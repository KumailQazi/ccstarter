.PHONY: test probe coverage corpus clean

test:            ## everything that works offline (no internet needed)
	python -m unittest discover -s tests -p 'test_*.py' -v

probe:           ## step 1: one record, one byte range
	python examples/01_probe_a_record.py $(DOMAIN)

coverage:        ## step 2: language mix of .pk
	python examples/02_urdu_coverage.py --tld pk --shards 8 --out pk_languages.csv

corpus:          ## step 4: a small JSONL corpus
	python examples/04_batch_extract.py --tld pk --max-records 200

clean:
	rm -f *.jsonl pk_languages.csv
