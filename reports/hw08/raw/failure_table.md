| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery (Part 1 worker, CREATE_INCIDENT replay) | 2 incident(s) created by 2 deliveries of one correlation_id -> extra side effect (run 205006) | 1 incident(s) created by 2 deliveries of one correlation_id -> no extra side effect (run 205211) |
| Duplicate delivery (Writer, task replay) | 2 draft(s) produced for 2 deliveries of one correlation_id (run 205308) | 1 draft(s) produced for 2 deliveries of one correlation_id (run 205344) |
| Consumer killed mid-work | redelivered after restart: False; drafts produced: 0; committed offset after kill=6, at the end=6 (run 205419) | redelivered after restart: True; drafts produced: 1; committed offset after kill=0, at the end=1 (run 205809) |
| Poison message | poison attempts in 15s window: 17; dead-lettered: False; later good message processed: False (run 210133) | poison attempts in 15s window: 3; dead-lettered: True; later good message processed: True (run 210335) |
| Two partitions/two consumers | 20/20 processed; 4/4 incidents spread over both partitions; 3 ordering inversions (run 210504) | 20/20 processed; 0/4 incidents spread over both partitions; 0 ordering inversions (run 210752) |
