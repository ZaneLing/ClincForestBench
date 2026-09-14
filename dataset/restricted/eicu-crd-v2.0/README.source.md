# eICU Collaborative Research Database v2.0 local source

- Access class: PhysioNet credentialed health data.
- Local payload: approximately 5.1 GB across 31 compressed CSV tables.
- Integrity metadata: upstream `SHA256SUMS.txt` retained.
- License metadata: PhysioNet Credentialed Health Data License 1.4.0 retained
  in `LICENSE.txt`.
- Intended benchmark role: ICU early assessment, monitoring, intervention,
  and outcome trajectories.

The supplied license prohibits sharing access to the restricted data. Raw
`*.csv.gz` tables therefore remain local and are excluded from Git. This note,
the upstream license, and checksum manifest are safe repository metadata; they
do not grant access to the underlying records.
