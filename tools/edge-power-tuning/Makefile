VERSION ?= 1.0.0
ARCH ?= amd64

.PHONY: deb
deb:
	docker run --rm -e VERSION=$(VERSION) -e ARCH=$(ARCH) -v $(PWD):/tmp -w /tmp goreleaser/nfpm package \
		--config /tmp/nfpm.yaml \
		--target /tmp \
		--packager deb