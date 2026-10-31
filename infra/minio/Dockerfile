# Public MinIO images were removed in 2026. Build the archived official source at an immutable SHA.
FROM golang:1.24.8-bookworm AS builder
ARG MINIO_COMMIT=7aac2a2c5b7c882e68c1ce017d8256be2feea27f
RUN git init /src && cd /src && git remote add origin https://github.com/minio/minio.git && git fetch --depth 1 origin "$MINIO_COMMIT" && git checkout --detach FETCH_HEAD
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /out/minio .
FROM alpine:3.22
LABEL org.opencontainers.image.source="https://github.com/minio/minio" org.opencontainers.image.revision="7aac2a2c5b7c882e68c1ce017d8256be2feea27f" org.opencontainers.image.licenses="AGPL-3.0"
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 minio && mkdir /data && chown minio:minio /data
COPY --from=builder /out/minio /usr/local/bin/minio
COPY --from=builder /src/LICENSE /licenses/MinIO-AGPL-3.0.txt
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
