# Rotated two-pile bent validation data

`selected_experiment_processed.h5` contains the processed shake-table records
used to validate the rotated two-pile bent example. It is kept here temporarily
while the durable dataset is prepared in DesignSafe project `PRJ-6524`.

The file contains the common experimental time vector, free-field acceleration
records, bent-top response for 0, 30, 60, and 90 degree orientations, and pile
bending-moment profiles. The postprocessor treats acceleration as units of `g`,
displacement as metres, depth as metres, and moment as N m.

SHA-256:

```text
cbab6292fb10919bd4ce03e3e11bf09acc7fca05be5b1d16965f4322dc06803b  selected_experiment_processed.h5
```

Before publishing this file outside the Femora repository, replace this note
with the experiment citation, authorship, license, and DesignSafe DOI.
