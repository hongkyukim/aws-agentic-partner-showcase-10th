PY ?= python3
RUN = PYTHONPATH=src $(PY) -m agentic_stack

.PHONY: demo trace eval eval-bad gate test clean

demo:
	$(RUN) demo

trace:
	$(RUN) trace

eval:
	$(RUN) eval

eval-bad:
	$(RUN) eval --model-mode hallucinate

gate:
	$(RUN) gate --env staging --image "123456789012.dkr.ecr.us-west-2.amazonaws.com/refund-agent@sha256:$$(printf '%064d' 0)"

test:
	uv run --python 3.12 --with 'pytest>=8,<9' python -m pytest -q

clean:
	rm -rf reports/*.json reports/*.jsonl reports/*.md .pytest_cache
