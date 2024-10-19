# Verida API server

This repo contains the code to build enclave image to run verida API server. It uses a self signed certificate and enables HTTPS connection to the API server. The TLS session ends within the enclave so that data is secured end to end. 

## Pre requisites

To run the API server within enclave following pre requisites are necessary

1. Docker
2. A metamask account on Arbitrum one with some ETH(for gas) and some USDC(to pay for oyster enclave)

## Build enclave

Enclave can be built by running the following command

```sh
docker build -t enclave .
docker run -it --privileged -v `pwd`:/app/mount enclave
```

This creates a folder named `enclave` which will contain the enclave image file named `enclave.eif`. Please use this image to deploy the enclave.

Note: Current repo assumes the build machine as well as enclave is arm64. If amd64 is used for building enclave, please replace all instances of arm64 to amd64 and use amd64 while deploying the enclave.

## Deploy enclave

To deploy the enclave please follow the guide in docs [here](https://docs.marlin.org/user-guides/oyster/instances/tutorials/nodejs-server/deploy).

## Interact with API server

Once enclave starts and an IP address is received for the enclave on the page, the server should be available at 5022 port.
