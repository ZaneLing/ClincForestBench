#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="$ROOT_DIR/dataset/interaction"
FORCE="${CFB_FORCE_DOWNLOAD:-0}"

download() {
  local url="$1"
  local output="$2"
  local partial="${output}.part"
  mkdir -p "$(dirname "$output")"
  if [[ -s "$output" && "$FORCE" != "1" ]]; then
    echo "[skip] ${output#$ROOT_DIR/}"
    return
  fi
  [[ "$FORCE" == "1" ]] && rm -f "$partial"
  echo "[download] ${output#$ROOT_DIR/}"
  curl --fail --location --retry 4 --retry-delay 2 --continue-at - \
    --output "$partial" "$url"
  mv "$partial" "$output"
}

download_rows() {
  local repo="$1"
  local config="$2"
  local split="$3"
  local length="$4"
  local output="$5"
  local partial="${output}.part"
  mkdir -p "$(dirname "$output")"
  if [[ -s "$output" && "$FORCE" != "1" ]]; then
    echo "[skip] ${output#$ROOT_DIR/}"
    return
  fi
  [[ "$FORCE" == "1" ]] && rm -f "$partial"
  echo "[download] ${output#$ROOT_DIR/}"
  curl --fail --location --retry 4 --get \
    --data-urlencode "dataset=$repo" \
    --data-urlencode "config=$config" \
    --data-urlencode "split=$split" \
    --data-urlencode "offset=0" \
    --data-urlencode "length=$length" \
    --output "$partial" \
    "https://datasets-server.huggingface.co/rows"
  mv "$partial" "$output"
}

download "https://huggingface.co/datasets/AQ-MedAI/PulseMind/raw/main/README.md" \
  "$DATA_DIR/mediscope/README.upstream.md"
download "https://huggingface.co/datasets/AQ-MedAI/PulseMind/resolve/main/CMtMedQA_diagnose.json" \
  "$DATA_DIR/mediscope/CMtMedQA_diagnose.json"
download "https://huggingface.co/datasets/AQ-MedAI/PulseMind/resolve/main/MedDiagnose.parquet" \
  "$DATA_DIR/mediscope/MedDiagnose.parquet"

download "https://huggingface.co/datasets/TheLumos/MedPI-Dataset/raw/main/README.md" \
  "$DATA_DIR/medpi/README.upstream.md"
for file in patients.csv conversations.csv dimensions.csv conversations_messages.jsonl; do
  download "https://huggingface.co/datasets/TheLumos/MedPI-Dataset/resolve/main/$file" \
    "$DATA_DIR/medpi/$file"
done

if [[ -d "$DATA_DIR/patientsim/source/.git" && "$FORCE" == "1" ]]; then
  git -C "$DATA_DIR/patientsim/source" pull --ff-only
elif [[ -d "$DATA_DIR/patientsim/source/.git" ]]; then
  echo "[skip] dataset/interaction/patientsim/source"
elif [[ ! -e "$DATA_DIR/patientsim/source" ]]; then
  git clone --depth 1 https://github.com/dek924/PatientSim.git \
    "$DATA_DIR/patientsim/source"
else
  echo "PatientSim target exists but is not a Git checkout: $DATA_DIR/patientsim/source" >&2
  exit 1
fi

download "https://huggingface.co/datasets/Meddies/meddies-persona-vie/raw/main/README.md" \
  "$DATA_DIR/meddies-persona-vie/README.upstream.md"
download_rows "Meddies/meddies-persona-vie" "default" "train" "12" \
  "$DATA_DIR/meddies-persona-vie/mvp_rows.json"

download "https://huggingface.co/datasets/Cyan27/MedMemoryBench/raw/main/README.md" \
  "$DATA_DIR/medmemorybench/README.upstream.md"
for file in personas events trap_events queries clinical_reports; do
  download "https://huggingface.co/datasets/Cyan27/MedMemoryBench/resolve/main/data/en/$file.parquet" \
    "$DATA_DIR/medmemorybench/$file.parquet"
done

download "https://huggingface.co/datasets/AQ-MedAI/MedDialogRubrics/raw/main/README.md" \
  "$DATA_DIR/meddialogrubrics/README.upstream.md"
download "https://huggingface.co/datasets/AQ-MedAI/MedDialogRubrics/resolve/main/MedDialogRubrics_v1.xlsx" \
  "$DATA_DIR/meddialogrubrics/MedDialogRubrics_v1.xlsx"

if command -v shasum >/dev/null 2>&1; then
  checksum=(shasum -a 256)
elif command -v sha256sum >/dev/null 2>&1; then
  checksum=(sha256sum)
else
  echo "Neither shasum nor sha256sum is installed." >&2
  exit 1
fi

find "$DATA_DIR" -type f ! -path '*/.git/*' ! -name 'SHA256SUMS.local.txt' -print0 \
  | sort -z \
  | xargs -0 "${checksum[@]}" \
  > "$DATA_DIR/SHA256SUMS.local.txt"

echo "Interaction MVP sources downloaded to $DATA_DIR"
