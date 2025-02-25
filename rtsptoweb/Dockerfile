# syntax=docker/dockerfile:1

FROM golang:1.22-alpine3.20 AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /go/src/app
COPY . .

ENV CGO_ENABLED=0 GO111MODULE=on

RUN go mod tidy && go mod download

RUN go build -o rtsp-to-web .

# --- Runtime Stage ---
FROM alpine:3.21

WORKDIR /app

COPY --from=builder /go/src/app/rtsp-to-web /app/
COPY --from=builder /go/src/app/web /app/web
COPY --from=builder /go/src/app/config.json /config/config.json

ENV GIN_MODE="release"

CMD ["/app/rtsp-to-web", "--config=/config/config.json"]