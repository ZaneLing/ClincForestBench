#!/usr/bin/env bash
# Recreate ClincForestBench source datasets without storing large payloads in Git.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATASET_DIR="$ROOT_DIR/dataset"
PROFILE="all"
FORCE="${CFB_FORCE_DOWNLOAD:-0}"

usage() {
  cat <<'EOF'
Usage: ./download_data.sh [all|core|interaction|restricted] [--force]

  all          Download public core datasets and the interaction MVP (default).
  core         Download DDXPlus, Synthea, PMC-Patients, clinical guidelines,
               NEJM/PubMed metadata, and restore MedAgentBench files if absent.
  interaction  Download the MediScope, MedPI, PatientSim demo, Meddies,
               MedMemoryBench, and MedDialogRubrics MVP source slice.
  restricted   Download credentialed PhysioNet sources after access approval.
               Requires wget and a configured ~/.netrc (recommended), or
               PHYSIONET_USERNAME for an interactive password prompt.

Set CFB_FORCE_DOWNLOAD=1 or pass --force to replace existing public files.
Restricted datasets are never downloaded by the default `all` profile.
EOF
}

for argument in "$@"; do
  case "$argument" in
    all|core|interaction|restricted) PROFILE="$argument" ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $argument" >&2; usage >&2; exit 2 ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

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
  curl --fail --location --retry 5 --retry-delay 2 --continue-at - \
    --output "$partial" "$url"
  mv "$partial" "$output"
}

verify_sha256() {
  local expected="$1"
  local file="$2"
  local actual
  if command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$file" | awk '{print $1}')"
  else
    echo "Neither shasum nor sha256sum is installed." >&2
    exit 1
  fi
  if [[ "$actual" != "$expected" ]]; then
    echo "Checksum mismatch: $file" >&2
    echo "expected $expected" >&2
    echo "actual   $actual" >&2
    exit 1
  fi
}

download_ddxplus() {
  local base="https://huggingface.co/datasets/aai530-group6/ddxplus/resolve"
  local target="$DATASET_DIR/ddxplus"
  download "$base/main/release_conditions.json" "$target/release_conditions.json"
  download "$base/main/release_evidences.json" "$target/release_evidences.json"
  download "$base/refs%2Fconvert%2Fparquet/default/test/0000.parquet" "$target/test.parquet"
  download "$base/refs%2Fconvert%2Fparquet/default/validate/0000.parquet" "$target/validate.parquet"
  download "$base/refs%2Fconvert%2Fparquet/default/train/0000.parquet" "$target/train-0000.parquet"
  download "$base/refs%2Fconvert%2Fparquet/default/train/0001.parquet" "$target/train-0001.parquet"
}

download_synthea() {
  local target="$DATASET_DIR/synthea"
  local archive="$target/synthea_sample_data_csv_apr2020.zip"
  download \
    "https://synthetichealth.github.io/synthea-sample-data/downloads/synthea_sample_data_csv_apr2020.zip" \
    "$archive"
  verify_sha256 \
    "4194b18c11eaedcf0d5d5dd448d8ac9661f14381e2ef9f109215dc42266cd38a" \
    "$archive"
  if [[ "$FORCE" == "1" || ! -s "$target/csv/patients.csv" ]]; then
    need unzip
    echo "[extract] dataset/synthea/csv"
    unzip -oq "$archive" -d "$target"
  fi
}

download_medagentbench() {
  local commit="99260117137b09f04837a8c18d18a1107efa55ae"
  local base="https://raw.githubusercontent.com/stanfordmlgroup/MedAgentBench/$commit"
  local target="$DATASET_DIR/medagentbench"
  download "$base/README.md" "$target/README.upstream.md"
  download "$base/LICENSE" "$target/LICENSE.upstream"
  for file in test_data_v1.json test_data_v2.json funcs_v1.json web.html final_web.html; do
    download "$base/data/medagentbench/$file" "$target/$file"
  done
}

download_pmc_and_guidelines() {
  download \
    "https://huggingface.co/datasets/zhengyun21/PMC-Patients/resolve/main/PMC-Patients.csv" \
    "$DATASET_DIR/pmc_case_reports/PMC-Patients.csv"
  local base="https://huggingface.co/datasets/epfl-llm/guidelines/resolve/refs%2Fconvert%2Fparquet/default/train"
  download "$base/0000.parquet" "$DATASET_DIR/clinical_guidelines/train-0000.parquet"
  download "$base/0001.parquet" "$DATASET_DIR/clinical_guidelines/train-0001.parquet"
}

download_nejm_pubmed() {
  local target="$DATASET_DIR/nejm_cpc"
  local query="Case Records of the Massachusetts General Hospital[Title]"
  local search_xml="$target/.pubmed_search.xml.part"
  local query_key web_env records_partial
  mkdir -p "$target"

  if [[ ! -s "$target/pubmed_search.json" || "$FORCE" == "1" ]]; then
    echo "[download] dataset/nejm_cpc/pubmed_search.json"
    curl --fail --location --retry 5 --get \
      --data-urlencode "db=pubmed" --data-urlencode "term=$query" \
      --data-urlencode "retmax=10000" --data-urlencode "retmode=json" \
      --data-urlencode "tool=ClincForestBench" \
      --output "$target/pubmed_search.json.part" \
      "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    mv "$target/pubmed_search.json.part" "$target/pubmed_search.json"
  else
    echo "[skip] dataset/nejm_cpc/pubmed_search.json"
  fi

  if [[ -s "$target/pubmed_records.xml" && "$FORCE" != "1" ]]; then
    echo "[skip] dataset/nejm_cpc/pubmed_records.xml"
    return
  fi
  echo "[query] NEJM CPC PubMed history"
  curl --fail --location --retry 5 --get \
    --data-urlencode "db=pubmed" --data-urlencode "term=$query" \
    --data-urlencode "retmax=0" --data-urlencode "usehistory=y" \
    --data-urlencode "tool=ClincForestBench" --output "$search_xml" \
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
  query_key="$(sed -n 's:.*<QueryKey>\([^<]*\)</QueryKey>.*:\1:p' "$search_xml" | head -1)"
  web_env="$(sed -n 's:.*<WebEnv>\([^<]*\)</WebEnv>.*:\1:p' "$search_xml" | head -1)"
  rm -f "$search_xml"
  if [[ -z "$query_key" || -z "$web_env" ]]; then
    echo "Could not establish an NCBI history session." >&2
    exit 1
  fi
  records_partial="$target/pubmed_records.xml.part"
  echo "[download] dataset/nejm_cpc/pubmed_records.xml"
  curl --fail --location --retry 5 --get \
    --data-urlencode "db=pubmed" --data-urlencode "query_key=$query_key" \
    --data-urlencode "WebEnv=$web_env" --data-urlencode "retmode=xml" \
    --data-urlencode "retmax=10000" --data-urlencode "tool=ClincForestBench" \
    --output "$records_partial" \
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
  mv "$records_partial" "$target/pubmed_records.xml"
}

download_core() {
  need curl
  download_ddxplus
  download_synthea
  download_medagentbench
  download_pmc_and_guidelines
  download_nejm_pubmed
}

download_interaction() {
  need curl
  need git
  CFB_FORCE_DOWNLOAD="$FORCE" bash "$ROOT_DIR/scripts/data/download_interaction_mvp.sh"
}

download_restricted() {
  need wget
  local auth=()
  if [[ -n "${PHYSIONET_USERNAME:-}" ]]; then
    auth=(--user "$PHYSIONET_USERNAME" --ask-password)
  elif [[ ! -f "$HOME/.netrc" ]]; then
    cat >&2 <<'EOF'
Restricted download requires approved PhysioNet access.
Configure ~/.netrc for physionet.org or export PHYSIONET_USERNAME; this script
will not accept or persist a password/token in the repository.
EOF
    exit 1
  else
    auth=(--netrc)
  fi
  local specs=(
    "mc-med/1.0.1|restricted/mc-med-v1.0.1"
    "eicu-crd/2.0|restricted/eicu-crd-v2.0"
    "mimiciv/3.1|restricted/mimiciv/3.1"
    "mimic-iv-ed/2.2|restricted/mimic-iv-ed-v2.2"
    "mimic-iv-note/2.2|restricted/mimic-iv-note/2.2"
    "mimic-iv-ecg/1.0|restricted/mimic-iv-ecg"
    "persona-patientsim/1.0.0|interaction/patientsim/physionet-1.0.0"
  )
  local spec remote target
  for spec in "${specs[@]}"; do
    remote="${spec%%|*}"
    target="$DATASET_DIR/${spec#*|}"
    mkdir -p "$target"
    echo "[restricted] $remote -> ${target#$ROOT_DIR/}"
    wget --recursive --no-parent --continue --timestamping \
      --no-host-directories --cut-dirs=3 --reject 'index.html*' \
      --directory-prefix "$target" "${auth[@]}" \
      "https://physionet.org/files/$remote/"
  done
}

case "$PROFILE" in
  all) download_core; download_interaction ;;
  core) download_core ;;
  interaction) download_interaction ;;
  restricted) download_restricted ;;
esac

echo "Data profile '$PROFILE' is ready under $DATASET_DIR"
