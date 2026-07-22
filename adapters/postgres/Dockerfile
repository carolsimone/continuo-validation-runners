FROM python:3.12-slim

# Runner image = core + exactly ONE adapter package. Engine selection happens here,
# at build time — there is no engine env var; the entry point IS the selection.
COPY core /src/core
COPY adapters/postgres /src/adapters/postgres
RUN pip install --no-cache-dir /src/core /src/adapters/postgres && rm -rf /src

# Continuo's executor-controller invokes `python /validation_runner.py`.
COPY docker/validation_runner_shim.py /validation_runner.py

RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

# Reads code from the image, writes only to stdout — run unprivileged.
USER 65532:65532

ENTRYPOINT []
CMD ["python", "/validation_runner.py"]
