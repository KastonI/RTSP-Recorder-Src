# syntax=docker/dockerfile:1

FROM golang:1.22-alpine3.20 AS builder

RUN apk add --no-cache git

WORKDIR /go/src/app
COPY . .

ARG TARGETOS TARGETARCH TARGETVARIANT

ENV CGO_ENABLED=0

RUN go get -u golang.org/x/crypto \
    && go mod download \
    && go build -a -o rtsp-to-web

FROM alpine:3.21

WORKDIR /app

COPY --from=builder /go/src/app/rtsp-to-web /app/
COPY --from=builder /go/src/app/web /app/web

RUN mkdir -p /config
COPY --from=builder /go/src/app/config.json /config

ENV GO111MODULE="on"
ENV GIN_MODE="release"

CMD ["./rtsp-to-web", "--config=/config/config.json"]
