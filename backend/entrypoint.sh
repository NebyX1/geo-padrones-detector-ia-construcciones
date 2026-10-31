#!/bin/sh
set -eu
# Migration is a single Compose init task, never an API replica startup side effect.
exec "$@"
