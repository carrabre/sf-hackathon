from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from openai import OpenAI
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import anthropic
import requests
import os
import re
import logging
import json
import time
import speech_recognition as sr

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def homepage_view(request):
    logger.info("Rendering homepage")
    return render(request, 'pryv/homepage.html')

def chat_view(request):
    logger.info("Rendering chat view")
    return render(request, 'chat.html')

@api_view(['POST'])
def handle_query(request):
    query = request.data.get('query')
    model_name = request.data.get('model')
    logger.info(f"Received query: {query} for model: {model_name}")

    try:
        if model_name in ['gpt-4', 'gpt-4-turbo-2024-04-09', 'gpt-4o']:
            # OpenAI GPT-4 models
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": query}]
            )
            reply = response.choices[0].message.content.strip()
            logger.info(f"Received response from {model_name}")
        
        elif model_name == 'llama':
            # LLaMA via Kuzco API (non-streaming)
            api_key = settings.KUZCO_API_KEY
            url = "https://api.kuzco.xyz/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": [{"role": "user", "content": query}],
                "model": "llama3:latest",
                "stream": False
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                reply = response.json()['choices'][0]['message']['content'].strip()
                logger.info("Received response from LLaMA")
            else:
                error_message = response.json().get('error', {}).get('message', '')
                logger.error(f"Error from LLaMA API: {response.status_code}, {error_message}")
                reply = f"Error: {response.status_code}, {error_message}"
        
        elif model_name in ['claude-3-5-sonnet', 'claude-3-opus']:
            # Anthropic's Claude
            anthropic_client = anthropic.Anthropic(api_key=claude_api_key)
            response = anthropic_client.messages.create(
                system="You are a world-class AI assistant.",
                model=model_name + "-20240620" if model_name == 'claude-3-5-sonnet' else model_name + "-20240229",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": query
                            }
                        ]
                    }
                ],
                max_tokens=1000,
            )
            reply = response.content[0].text
            logger.info(f"Received response from {model_name}")
        
        else:
            reply = f"Model {model_name} not supported"
            logger.error(reply)
        
        return Response({"reply": reply})
    
    except Exception as e:
        logger.error(f"Error handling query: {str(e)}")
        return Response({"error": str(e)}, status=500)

@csrf_exempt
def stream_query(request):
    query = request.GET.get('query')
    model_name = request.GET.get('model')
    context = json.loads(request.GET.get('context', '[]'))
    logger.info(f"Streaming query: {query} for model: {model_name} with context: {context}")

    def event_stream():
        try:
            response_generator = get_model_response(model_name, query, context)
            for chunk in response_generator:
                if isinstance(chunk, str):
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                elif isinstance(chunk, dict):  # For OpenAI-style chunks
                    content = chunk.get('choices', [{}])[0].get('delta', {}).get('content')
                    if content:
                        yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                else:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"  # Send keepalive
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception(f"Error in event_stream: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"  # Ensure [DONE] is sent even if there's an error

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

def get_model_response(model_name, query, context):
    messages = [{"role": "system", "content": "You are a helpful assistant."}] + context + [{"role": "user", "content": query}]
    
    if model_name in ['gpt-4', 'gpt-4-turbo-2024-04-09', 'gpt-4o']:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"Sending request to OpenAI API for model: {model_name}")
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
        )
        logger.info(f"Received response from OpenAI API for model: {model_name}")
        for chunk in response:
            logger.info(f"Received chunk from OpenAI API: {chunk}")
            yield chunk
    elif model_name in ['claude-3-5-sonnet', 'claude-3-opus']:
        anthropic_client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
        with anthropic_client.messages.stream(
            max_tokens=4096,
            messages=[{"role": m["role"], "content": [{"type": "text", "text": m["content"]}]} for m in messages[1:]],  # Exclude the system message for Claude
            model=model_name + "-20240620" if model_name == 'claude-3-5-sonnet' else model_name + "-20240229",
        ) as stream:
            for text in stream.text_stream:
                yield text
    elif model_name == 'llama':
        api_key = settings.KUZCO_API_KEY
        url = "https://api.kuzco.xyz/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "messages": messages,
            "model": "llama3:latest",
            "stream": True
        }

        try:
            with requests.post(url, headers=headers, json=payload, stream=True, timeout=90) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            if line.startswith('data: '):
                                data = json.loads(line[6:])
                                if data['choices'][0]['delta'].get('content'):
                                    yield data['choices'][0]['delta']['content']
                else:
                    error_message = f"Error from LLaMA API: {response.status_code}, {response.text}"
                    logger.error(error_message)
                    yield error_message
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to LLaMA API failed: {str(e)}")
            yield f"Error: Connection to LLaMA API failed - {str(e)}"
    else:
        yield f"Model {model_name} not supported"

@csrf_exempt
def process_audio(request):
    if request.method == 'POST' and request.FILES.get('audio'):
        recognizer = sr.Recognizer()
        audio_file = request.FILES['audio']
        
        try:
            with sr.AudioFile(audio_file) as source:
                audio = recognizer.record(source)
            
            # Attempt to recognize the speech
            text = recognizer.recognize_google(audio)
            return JsonResponse({'transcript': text})
        except sr.UnknownValueError:
            return JsonResponse({'error': 'Could not understand audio'}, status=400)
        except sr.RequestError as e:
            return JsonResponse({'error': f'Error with the speech recognition service: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
