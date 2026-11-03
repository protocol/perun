FROM golang:1.27.3 AS build
WORKDIR /src
COPY . .
RUN go build -o /worker .

FROM alpine:3.24.3
COPY --from=build /worker /worker
CMD ["/worker"]
