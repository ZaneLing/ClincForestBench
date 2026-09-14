#!/usr/bin/env bash
set -euo pipefail

node_version="v24.20.0"
machine="$(uname -m)"
case "$machine" in
  arm64) node_arch="arm64" ;;
  x86_64) node_arch="x64" ;;
  *) echo "Unsupported architecture: $machine" >&2; exit 1 ;;
esac
target=".tools/node-${node_version#v}-darwin-${node_arch}"
if [ ! -x "$target/bin/node" ]; then
  mkdir -p .tools
  temporary="$(mktemp -d)"
  curl -fsSL "https://nodejs.org/dist/${node_version}/node-${node_version}-darwin-${node_arch}.tar.gz" -o "$temporary/node.tar.gz"
  tar -xzf "$temporary/node.tar.gz" -C .tools
fi
ln -sfn "$(basename "$target")" .tools/node
.tools/node/bin/node --version

