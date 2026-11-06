# HW9 labeling notes (cache_cases.yaml) - Kazi Samina Maraj Mumu

cache_cases.yaml was committed before the threshold sweep and has not been edited.
Mistakes found afterwards are documented here instead.

- The labels were written from the HW4 seed script, but my s4098_rel has different
  route codes (RT-001 Green Line, RT-002 Orange Line, RT-003 Route 22, RT-004 Route 522,
  RT-005 Route 55) and incident codes shifted by one (INC-000042 is titled "...Incident 41").
  The route-code list in the YAML header comment and the notes on C22/C30 are therefore wrong
  for my database; the hit/miss labels do not depend on them.
- C24 (INC-000043 vs INC-000042, "What category is incident ...?"): in my database both
  incidents are infrastructure-issue, so the category is the same. The cached answer still
  names the wrong incident (INC-000042). Kept as labeled (should miss) and counted as a false
  hit. Removing it would not change the chosen threshold (0.95), because C24 is a false hit
  at every threshold.
- All other similar_different pairs (C21-C23, C25-C30) were checked against s4098_rel and do
  have different correct answers.
