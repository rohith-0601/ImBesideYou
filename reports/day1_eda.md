# Day 1 EDA — dataset_b

Loaded **20,477** events across **15** sessions.

## 1. Session shape

| session_id                          | machine         |   n_events |   duration_min |
|:------------------------------------|:----------------|-----------:|---------------:|
| ses_20260701-164424-CHAITANYA0BCF   | CHAITANYA0BCF   |       1613 |           11.4 |
| ses_20260701-171614-CHAITANYA0BCF   | CHAITANYA0BCF   |       2015 |           14   |
| ses_20260701-173246-SIDDHIGUPTAB00B | SIDDHIGUPTAB00B |       1439 |           12.8 |
| ses_20260701-173642-NEELA9BAF       | NEELA9BAF       |       1136 |           10.3 |
| ses_20260701-175258-LAPTOP-76QMG9DE | LAPTOP-76QMG9DE |       1550 |           13.6 |
| ses_20260701-175747-SIDDHIGUPTAB00B | SIDDHIGUPTAB00B |       1309 |           11.5 |
| ses_20260701-180923-NEELA9BAF       | NEELA9BAF       |       1349 |           12.7 |
| ses_20260701-181413-LAPTOP-76QMG9DE | LAPTOP-76QMG9DE |       1518 |           13.1 |
| ses_20260701-181913-SIDDHIGUPTAB00B | SIDDHIGUPTAB00B |       1165 |           10.3 |
| ses_20260701-182634-NEELA9BAF       | NEELA9BAF       |       1001 |           10.5 |
| ses_20260701-183232-LAPTOP-76QMG9DE | LAPTOP-76QMG9DE |        781 |            7.2 |
| ses_20260701-184201-LAPTOP-76QMG9DE | LAPTOP-76QMG9DE |       1895 |           16.4 |
| ses_20260701-190250-NEELA9BAF       | NEELA9BAF       |       1146 |           10.1 |
| ses_20260701-191537-LAPTOP-76QMG9DE | LAPTOP-76QMG9DE |       1562 |           11.3 |
| ses_20260701-192455-NEELA9BAF       | NEELA9BAF       |        998 |           11.1 |

Total wall-clock across sessions: 176 min (sessions do not overlap in time per machine, but do across the 4 operators).

## 2. Inter-event gap distribution (candidate idle threshold)

Percentiles of `ms_since_last_event` (all events, session-internal gaps only; first event of each chunk has no prior gap):

|       |   seconds |
|------:|----------:|
| 0.5   |      0.03 |
| 0.75  |      0.22 |
| 0.9   |      1.54 |
| 0.95  |      2.08 |
| 0.99  |      5.47 |
| 0.995 |      6.69 |
| 0.999 |     10.13 |

- gaps > 30s: 7 (0.04%)
- gaps > 60s: 4 (0.02%)
- gaps > 120s: 3 (0.02%)

Note: per README, waiting time in this test environment is compressed vs. production, so an idle-gap threshold alone will likely under-segment — cross-checked against app/URL switches below, not used in isolation.

## 3. Application usage

| app_name               |   event_count |
|:-----------------------|--------------:|
| Microsoft Edge         |         13300 |
| Microsoft Word         |          3704 |
| Microsoft Excel        |          1201 |
| OpenWith               |           757 |
| Notepad                |           599 |
| WindowsTerminal        |           407 |
| procmine-desktop-agent |           205 |
| Windows Explorer       |            78 |
| ms-teams               |            73 |
| prl_cc                 |            28 |

`app_switch` events: 1654 total, 110.3 per session on average.

## 4. Portal route usage (from active_browser_tab.url)

|                                            |   event_count |
|:-------------------------------------------|--------------:|
| ('127.0.0.1:5132', '#/payroll-items')      |          1753 |
| ('127.0.0.1:5133', '#/payroll-items')      |           991 |
| ('127.0.0.1:5134', '#/payroll-items')      |           969 |
| ('127.0.0.1:5133', '#/resident-tax')       |           925 |
| ('127.0.0.1:5132', '#/onboarding')         |           863 |
| ('127.0.0.1:5134', '#/leave-applications') |           803 |
| ('127.0.0.1:5132', '#/leave-applications') |           765 |
| ('127.0.0.1:5134', '#/social-insurance')   |           608 |
| ('127.0.0.1:5133', '#/onboarding')         |           544 |
| ('127.0.0.1:5132', '#/social-insurance')   |           460 |
| ('127.0.0.1:5133', '#/leave-applications') |           431 |
| ('127.0.0.1:5133', '#/social-insurance')   |           148 |
| ('127.0.0.1:5134', '#/dashboard')          |            58 |
| ('127.0.0.1:5132', '#/dashboard')          |            14 |
| ('127.0.0.1:5133', '#/dashboard')          |            13 |

Distinct portal hosts seen: ['127.0.0.1:5132', '127.0.0.1:5133', '127.0.0.1:5134']

## 5. Route-revisit pattern (evidence of interleaved work)

| session_id                          |   distinct_routes |   route_transitions |
|:------------------------------------|------------------:|--------------------:|
| ses_20260701-164424-CHAITANYA0BCF   |                 5 |                  10 |
| ses_20260701-171614-CHAITANYA0BCF   |                 5 |                  15 |
| ses_20260701-173246-SIDDHIGUPTAB00B |                 6 |                  14 |
| ses_20260701-173642-NEELA9BAF       |                 5 |                  12 |
| ses_20260701-175258-LAPTOP-76QMG9DE |                 5 |                  11 |
| ses_20260701-175747-SIDDHIGUPTAB00B |                 5 |                  11 |
| ses_20260701-180923-NEELA9BAF       |                 6 |                  14 |
| ses_20260701-181413-LAPTOP-76QMG9DE |                 5 |                  13 |
| ses_20260701-181913-SIDDHIGUPTAB00B |                 4 |                   8 |
| ses_20260701-182634-NEELA9BAF       |                 4 |                  12 |
| ses_20260701-183232-LAPTOP-76QMG9DE |                 4 |                   5 |
| ses_20260701-184201-LAPTOP-76QMG9DE |                 6 |                  13 |
| ses_20260701-190250-NEELA9BAF       |                 4 |                   6 |
| ses_20260701-191537-LAPTOP-76QMG9DE |                 4 |                   9 |

Multiple distinct routes with many transitions per session is the interleaving pattern the README warns about ('a person switches to a different task partway through one, then returns to it later') — segmentation cannot assume one route = one contiguous block.
