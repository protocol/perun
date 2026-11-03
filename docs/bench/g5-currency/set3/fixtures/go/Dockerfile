FROM golang:1.21.0
WORKDIR /src
COPY . .
RUN go build -o /gatewayd .
ENTRYPOINT ["/gatewayd"]
