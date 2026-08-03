FROM public.ecr.aws/lambda/python:3.12

# torch (CPU-only build to keep the image smaller) + transformers
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu \
    transformers \
    boto3

COPY src/common ${LAMBDA_TASK_ROOT}/common
COPY src/model_scan/app.py ${LAMBDA_TASK_ROOT}/model_scan/app.py

# Pre-download TinyLlama weights into the image at build time, so cold
# starts don't pay a network download on top of the model load — this is
# the single biggest lever for keeping cold-start latency sane for a 1.1B
# model. Adds build time and image size (~2-3GB) in exchange for faster
# invocations.
RUN python3 -c "from transformers import pipeline; \
    pipeline('text-generation', model='TinyLlama/TinyLlama-1.1B-Chat-v1.0')"

CMD ["model_scan.app.handler"]
