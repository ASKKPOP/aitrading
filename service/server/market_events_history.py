"""Verified historical US macro-event calendar, 2019-01 through 2025-12.

For backtesting the event-window entry filter (see service/server/market_events.py).
Tuple format matches market_events._CALENDAR minus the leading event_type:
(local ET date "YYYY-MM-DD", local ET time "HH:MM", title).

Every date below was verified against primary sources; none are from memory.

Sources
-------
FOMC (statement release = day 2 of meeting, 14:00 ET unless noted):
  - 2019: https://www.federalreserve.gov/monetarypolicy/fomchistorical2019.htm
  - 2020: https://www.federalreserve.gov/monetarypolicy/fomchistorical2020.htm
    (scheduled March 17-18, 2020 meeting was cancelled; replaced by the
    unscheduled March 15 decision)
  - 2021-2025: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  - Second pass: every statement date confirmed by HTTP 200 + title
    "Federal Reserve issues FOMC statement" at
    https://www.federalreserve.gov/newsevents/pressreleases/monetary<YYYYMMDD>a.htm
    (all 57 dates). Emergency-statement release times read from the
    monetary20200303a / monetary20200315a pages ("For release at 10:00 a.m."
    / "5:00 p.m.").

CPI (08:30 ET) and Employment Situation / NFP (08:30 ET):
  - BLS schedule pages https://www.bls.gov/schedule/news_release/cpi.htm and
    https://www.bls.gov/schedule/news_release/empsit.htm via Wayback Machine
    snapshots (bls.gov returns 403 to non-browser clients; the pre-2017
    bls.gov/schedule/archives/{cpi,empsit}_nr.htm archive pages are gone).
    Snapshots used (web.archive.org/web/<ts>/...):
      CPI:    20190109024228 (2019), 20191216023559 (2020), 20210128124146 (2021),
              20220109075526 (2022), 20230104040906 (2023), 20240304183902 (2024),
              20250104044048 + 20260123232744 (2025 incl. shutdown changes);
              mid-year cross-checks 20200701165426, 20210721055333,
              20220701044115, 20230718182704, 20240726162146.
      EMPSIT: 20190109020429 (2019), 20191216030043 (2020), 20201210210550 (2021),
              20220110090111 (2022), 20230101123540 (2023), 20240307201049 (2024),
              20250104044052 + 20260104120716 (2025 incl. shutdown changes);
              mid-year cross-checks 20200807035002, 20210729201607,
              20220702001711, 20240804073753, 20250712141503.
  - Second pass: actual release dates independently confirmed from the BLS
    news-release archive filenames (bls.gov/news.release/archives/cpi_MMDDYYYY.htm,
    empsit_MMDDYYYY.htm — the filename encodes the true release date), enumerated
    via the Wayback CDX index. Both passes agree on every entry below.

2025 government-shutdown irregularities (both confirmed by the Jan 2026
schedule snapshots AND archive filenames):
  - CPI: Sep 2025 CPI delayed to 2025-10-24; the October 2025 CPI was never
    published; Nov 2025 CPI released 2025-12-18. 2025 has 11 CPI releases.
  - NFP: Sep 2025 Employment Situation delayed to 2025-11-20; no standalone
    October 2025 report (October data folded into the Nov 2025 report released
    2025-12-16). 2025 has 11 NFP releases.

Not included (not rate decisions / not requested): FOMC unscheduled
conference call of 2019-10-04 (statement 2019-10-11, balance-sheet only) and
the 2020 / 2025 notation votes (2020-03-19/23/31, 2020-08-27, 2025-08-22).

US election days: statutory Tuesday-after-first-Monday dates; 18:00 ET is an
approximate earliest-polls-close time, not an official release time.
"""

# ── FOMC rate decisions (statement day; 14:00 ET, exceptions noted) ─────────
FOMC_DECISIONS: list[tuple[str, str, str]] = [
    # 2019 (8 scheduled)
    ("2019-01-30", "14:00", "FOMC rate decision"),
    ("2019-03-20", "14:00", "FOMC rate decision"),
    ("2019-05-01", "14:00", "FOMC rate decision"),
    ("2019-06-19", "14:00", "FOMC rate decision"),
    ("2019-07-31", "14:00", "FOMC rate decision"),  # first 2019 cut
    ("2019-09-18", "14:00", "FOMC rate decision"),  # second cut
    ("2019-10-30", "14:00", "FOMC rate decision"),  # third cut
    ("2019-12-11", "14:00", "FOMC rate decision"),
    # 2020 (7 scheduled + 2 unscheduled; Mar 17-18 scheduled meeting cancelled)
    ("2020-01-29", "14:00", "FOMC rate decision"),
    ("2020-03-03", "10:00", "FOMC rate decision (unscheduled)"),  # emergency -50bp
    ("2020-03-15", "17:00", "FOMC rate decision (unscheduled)"),  # emergency -100bp
    ("2020-04-29", "14:00", "FOMC rate decision"),
    ("2020-06-10", "14:00", "FOMC rate decision"),
    ("2020-07-29", "14:00", "FOMC rate decision"),
    ("2020-09-16", "14:00", "FOMC rate decision"),
    ("2020-11-05", "14:00", "FOMC rate decision"),
    ("2020-12-16", "14:00", "FOMC rate decision"),
    # 2021 (8 scheduled)
    ("2021-01-27", "14:00", "FOMC rate decision"),
    ("2021-03-17", "14:00", "FOMC rate decision"),
    ("2021-04-28", "14:00", "FOMC rate decision"),
    ("2021-06-16", "14:00", "FOMC rate decision"),
    ("2021-07-28", "14:00", "FOMC rate decision"),
    ("2021-09-22", "14:00", "FOMC rate decision"),
    ("2021-11-03", "14:00", "FOMC rate decision"),
    ("2021-12-15", "14:00", "FOMC rate decision"),
    # 2022 (8 scheduled)
    ("2022-01-26", "14:00", "FOMC rate decision"),
    ("2022-03-16", "14:00", "FOMC rate decision"),
    ("2022-05-04", "14:00", "FOMC rate decision"),
    ("2022-06-15", "14:00", "FOMC rate decision"),
    ("2022-07-27", "14:00", "FOMC rate decision"),
    ("2022-09-21", "14:00", "FOMC rate decision"),
    ("2022-11-02", "14:00", "FOMC rate decision"),
    ("2022-12-14", "14:00", "FOMC rate decision"),
    # 2023 (8 scheduled)
    ("2023-02-01", "14:00", "FOMC rate decision"),
    ("2023-03-22", "14:00", "FOMC rate decision"),
    ("2023-05-03", "14:00", "FOMC rate decision"),
    ("2023-06-14", "14:00", "FOMC rate decision"),
    ("2023-07-26", "14:00", "FOMC rate decision"),
    ("2023-09-20", "14:00", "FOMC rate decision"),
    ("2023-11-01", "14:00", "FOMC rate decision"),
    ("2023-12-13", "14:00", "FOMC rate decision"),
    # 2024 (8 scheduled)
    ("2024-01-31", "14:00", "FOMC rate decision"),
    ("2024-03-20", "14:00", "FOMC rate decision"),
    ("2024-05-01", "14:00", "FOMC rate decision"),
    ("2024-06-12", "14:00", "FOMC rate decision"),
    ("2024-07-31", "14:00", "FOMC rate decision"),
    ("2024-09-18", "14:00", "FOMC rate decision"),
    ("2024-11-07", "14:00", "FOMC rate decision"),
    ("2024-12-18", "14:00", "FOMC rate decision"),
    # 2025 (8 scheduled; 2025-08-22 notation vote excluded)
    ("2025-01-29", "14:00", "FOMC rate decision"),
    ("2025-03-19", "14:00", "FOMC rate decision"),
    ("2025-05-07", "14:00", "FOMC rate decision"),
    ("2025-06-18", "14:00", "FOMC rate decision"),
    ("2025-07-30", "14:00", "FOMC rate decision"),
    ("2025-09-17", "14:00", "FOMC rate decision"),
    ("2025-10-29", "14:00", "FOMC rate decision"),
    ("2025-12-10", "14:00", "FOMC rate decision"),
]

# ── CPI releases (BLS, 08:30 ET) ────────────────────────────────────────────
CPI_RELEASES: list[tuple[str, str, str]] = [
    # 2019
    ("2019-01-11", "08:30", "CPI (Dec 2018)"),
    ("2019-02-13", "08:30", "CPI (Jan 2019)"),
    ("2019-03-12", "08:30", "CPI (Feb 2019)"),
    ("2019-04-10", "08:30", "CPI (Mar 2019)"),
    ("2019-05-10", "08:30", "CPI (Apr 2019)"),
    ("2019-06-12", "08:30", "CPI (May 2019)"),
    ("2019-07-11", "08:30", "CPI (Jun 2019)"),
    ("2019-08-13", "08:30", "CPI (Jul 2019)"),
    ("2019-09-12", "08:30", "CPI (Aug 2019)"),
    ("2019-10-10", "08:30", "CPI (Sep 2019)"),
    ("2019-11-13", "08:30", "CPI (Oct 2019)"),
    ("2019-12-11", "08:30", "CPI (Nov 2019)"),
    # 2020
    ("2020-01-14", "08:30", "CPI (Dec 2019)"),
    ("2020-02-13", "08:30", "CPI (Jan 2020)"),
    ("2020-03-11", "08:30", "CPI (Feb 2020)"),
    ("2020-04-10", "08:30", "CPI (Mar 2020)"),
    ("2020-05-12", "08:30", "CPI (Apr 2020)"),
    ("2020-06-10", "08:30", "CPI (May 2020)"),
    ("2020-07-14", "08:30", "CPI (Jun 2020)"),
    ("2020-08-12", "08:30", "CPI (Jul 2020)"),
    ("2020-09-11", "08:30", "CPI (Aug 2020)"),
    ("2020-10-13", "08:30", "CPI (Sep 2020)"),
    ("2020-11-12", "08:30", "CPI (Oct 2020)"),
    ("2020-12-10", "08:30", "CPI (Nov 2020)"),
    # 2021
    ("2021-01-13", "08:30", "CPI (Dec 2020)"),
    ("2021-02-10", "08:30", "CPI (Jan 2021)"),
    ("2021-03-10", "08:30", "CPI (Feb 2021)"),
    ("2021-04-13", "08:30", "CPI (Mar 2021)"),
    ("2021-05-12", "08:30", "CPI (Apr 2021)"),
    ("2021-06-10", "08:30", "CPI (May 2021)"),
    ("2021-07-13", "08:30", "CPI (Jun 2021)"),
    ("2021-08-11", "08:30", "CPI (Jul 2021)"),
    ("2021-09-14", "08:30", "CPI (Aug 2021)"),
    ("2021-10-13", "08:30", "CPI (Sep 2021)"),
    ("2021-11-10", "08:30", "CPI (Oct 2021)"),
    ("2021-12-10", "08:30", "CPI (Nov 2021)"),
    # 2022
    ("2022-01-12", "08:30", "CPI (Dec 2021)"),
    ("2022-02-10", "08:30", "CPI (Jan 2022)"),
    ("2022-03-10", "08:30", "CPI (Feb 2022)"),
    ("2022-04-12", "08:30", "CPI (Mar 2022)"),
    ("2022-05-11", "08:30", "CPI (Apr 2022)"),
    ("2022-06-10", "08:30", "CPI (May 2022)"),
    ("2022-07-13", "08:30", "CPI (Jun 2022)"),
    ("2022-08-10", "08:30", "CPI (Jul 2022)"),
    ("2022-09-13", "08:30", "CPI (Aug 2022)"),
    ("2022-10-13", "08:30", "CPI (Sep 2022)"),
    ("2022-11-10", "08:30", "CPI (Oct 2022)"),
    ("2022-12-13", "08:30", "CPI (Nov 2022)"),
    # 2023
    ("2023-01-12", "08:30", "CPI (Dec 2022)"),
    ("2023-02-14", "08:30", "CPI (Jan 2023)"),
    ("2023-03-14", "08:30", "CPI (Feb 2023)"),
    ("2023-04-12", "08:30", "CPI (Mar 2023)"),
    ("2023-05-10", "08:30", "CPI (Apr 2023)"),
    ("2023-06-13", "08:30", "CPI (May 2023)"),
    ("2023-07-12", "08:30", "CPI (Jun 2023)"),
    ("2023-08-10", "08:30", "CPI (Jul 2023)"),
    ("2023-09-13", "08:30", "CPI (Aug 2023)"),
    ("2023-10-12", "08:30", "CPI (Sep 2023)"),
    ("2023-11-14", "08:30", "CPI (Oct 2023)"),
    ("2023-12-12", "08:30", "CPI (Nov 2023)"),
    # 2024
    ("2024-01-11", "08:30", "CPI (Dec 2023)"),
    ("2024-02-13", "08:30", "CPI (Jan 2024)"),
    ("2024-03-12", "08:30", "CPI (Feb 2024)"),
    ("2024-04-10", "08:30", "CPI (Mar 2024)"),
    ("2024-05-15", "08:30", "CPI (Apr 2024)"),
    ("2024-06-12", "08:30", "CPI (May 2024)"),
    ("2024-07-11", "08:30", "CPI (Jun 2024)"),
    ("2024-08-14", "08:30", "CPI (Jul 2024)"),
    ("2024-09-11", "08:30", "CPI (Aug 2024)"),
    ("2024-10-10", "08:30", "CPI (Sep 2024)"),
    ("2024-11-13", "08:30", "CPI (Oct 2024)"),
    ("2024-12-11", "08:30", "CPI (Nov 2024)"),
    # 2025 (11 releases: Oct 2025 CPI never published — government shutdown)
    ("2025-01-15", "08:30", "CPI (Dec 2024)"),
    ("2025-02-12", "08:30", "CPI (Jan 2025)"),
    ("2025-03-12", "08:30", "CPI (Feb 2025)"),
    ("2025-04-10", "08:30", "CPI (Mar 2025)"),
    ("2025-05-13", "08:30", "CPI (Apr 2025)"),
    ("2025-06-11", "08:30", "CPI (May 2025)"),
    ("2025-07-15", "08:30", "CPI (Jun 2025)"),
    ("2025-08-12", "08:30", "CPI (Jul 2025)"),
    ("2025-09-11", "08:30", "CPI (Aug 2025)"),
    ("2025-10-24", "08:30", "CPI (Sep 2025)"),  # delayed by shutdown (orig. 10-15)
    ("2025-12-18", "08:30", "CPI (Nov 2025)"),  # Oct 2025 CPI skipped entirely
]

# ── Employment Situation / nonfarm payrolls (BLS, 08:30 ET) ─────────────────
NFP_RELEASES: list[tuple[str, str, str]] = [
    # 2019
    ("2019-01-04", "08:30", "Jobs report (Dec 2018)"),
    ("2019-02-01", "08:30", "Jobs report (Jan 2019)"),
    ("2019-03-08", "08:30", "Jobs report (Feb 2019)"),
    ("2019-04-05", "08:30", "Jobs report (Mar 2019)"),
    ("2019-05-03", "08:30", "Jobs report (Apr 2019)"),
    ("2019-06-07", "08:30", "Jobs report (May 2019)"),
    ("2019-07-05", "08:30", "Jobs report (Jun 2019)"),
    ("2019-08-02", "08:30", "Jobs report (Jul 2019)"),
    ("2019-09-06", "08:30", "Jobs report (Aug 2019)"),
    ("2019-10-04", "08:30", "Jobs report (Sep 2019)"),
    ("2019-11-01", "08:30", "Jobs report (Oct 2019)"),
    ("2019-12-06", "08:30", "Jobs report (Nov 2019)"),
    # 2020
    ("2020-01-10", "08:30", "Jobs report (Dec 2019)"),  # 2nd Friday (ref-week shift)
    ("2020-02-07", "08:30", "Jobs report (Jan 2020)"),
    ("2020-03-06", "08:30", "Jobs report (Feb 2020)"),
    ("2020-04-03", "08:30", "Jobs report (Mar 2020)"),
    ("2020-05-08", "08:30", "Jobs report (Apr 2020)"),  # 2nd Friday
    ("2020-06-05", "08:30", "Jobs report (May 2020)"),
    ("2020-07-02", "08:30", "Jobs report (Jun 2020)"),  # Thursday (Jul 4 holiday)
    ("2020-08-07", "08:30", "Jobs report (Jul 2020)"),
    ("2020-09-04", "08:30", "Jobs report (Aug 2020)"),
    ("2020-10-02", "08:30", "Jobs report (Sep 2020)"),
    ("2020-11-06", "08:30", "Jobs report (Oct 2020)"),
    ("2020-12-04", "08:30", "Jobs report (Nov 2020)"),
    # 2021
    ("2021-01-08", "08:30", "Jobs report (Dec 2020)"),  # 2nd Friday
    ("2021-02-05", "08:30", "Jobs report (Jan 2021)"),
    ("2021-03-05", "08:30", "Jobs report (Feb 2021)"),
    ("2021-04-02", "08:30", "Jobs report (Mar 2021)"),
    ("2021-05-07", "08:30", "Jobs report (Apr 2021)"),
    ("2021-06-04", "08:30", "Jobs report (May 2021)"),
    ("2021-07-02", "08:30", "Jobs report (Jun 2021)"),
    ("2021-08-06", "08:30", "Jobs report (Jul 2021)"),
    ("2021-09-03", "08:30", "Jobs report (Aug 2021)"),
    ("2021-10-08", "08:30", "Jobs report (Sep 2021)"),  # 2nd Friday
    ("2021-11-05", "08:30", "Jobs report (Oct 2021)"),
    ("2021-12-03", "08:30", "Jobs report (Nov 2021)"),
    # 2022
    ("2022-01-07", "08:30", "Jobs report (Dec 2021)"),
    ("2022-02-04", "08:30", "Jobs report (Jan 2022)"),
    ("2022-03-04", "08:30", "Jobs report (Feb 2022)"),
    ("2022-04-01", "08:30", "Jobs report (Mar 2022)"),
    ("2022-05-06", "08:30", "Jobs report (Apr 2022)"),
    ("2022-06-03", "08:30", "Jobs report (May 2022)"),
    ("2022-07-08", "08:30", "Jobs report (Jun 2022)"),  # 2nd Friday
    ("2022-08-05", "08:30", "Jobs report (Jul 2022)"),
    ("2022-09-02", "08:30", "Jobs report (Aug 2022)"),
    ("2022-10-07", "08:30", "Jobs report (Sep 2022)"),
    ("2022-11-04", "08:30", "Jobs report (Oct 2022)"),
    ("2022-12-02", "08:30", "Jobs report (Nov 2022)"),
    # 2023
    ("2023-01-06", "08:30", "Jobs report (Dec 2022)"),
    ("2023-02-03", "08:30", "Jobs report (Jan 2023)"),
    ("2023-03-10", "08:30", "Jobs report (Feb 2023)"),  # 2nd Friday
    ("2023-04-07", "08:30", "Jobs report (Mar 2023)"),  # Good Friday
    ("2023-05-05", "08:30", "Jobs report (Apr 2023)"),
    ("2023-06-02", "08:30", "Jobs report (May 2023)"),
    ("2023-07-07", "08:30", "Jobs report (Jun 2023)"),
    ("2023-08-04", "08:30", "Jobs report (Jul 2023)"),
    ("2023-09-01", "08:30", "Jobs report (Aug 2023)"),
    ("2023-10-06", "08:30", "Jobs report (Sep 2023)"),
    ("2023-11-03", "08:30", "Jobs report (Oct 2023)"),
    ("2023-12-08", "08:30", "Jobs report (Nov 2023)"),  # 2nd Friday
    # 2024
    ("2024-01-05", "08:30", "Jobs report (Dec 2023)"),
    ("2024-02-02", "08:30", "Jobs report (Jan 2024)"),
    ("2024-03-08", "08:30", "Jobs report (Feb 2024)"),  # 2nd Friday
    ("2024-04-05", "08:30", "Jobs report (Mar 2024)"),
    ("2024-05-03", "08:30", "Jobs report (Apr 2024)"),
    ("2024-06-07", "08:30", "Jobs report (May 2024)"),
    ("2024-07-05", "08:30", "Jobs report (Jun 2024)"),
    ("2024-08-02", "08:30", "Jobs report (Jul 2024)"),
    ("2024-09-06", "08:30", "Jobs report (Aug 2024)"),
    ("2024-10-04", "08:30", "Jobs report (Sep 2024)"),
    ("2024-11-01", "08:30", "Jobs report (Oct 2024)"),
    ("2024-12-06", "08:30", "Jobs report (Nov 2024)"),
    # 2025 (11 releases: no standalone Oct 2025 report — government shutdown)
    ("2025-01-10", "08:30", "Jobs report (Dec 2024)"),  # 2nd Friday
    ("2025-02-07", "08:30", "Jobs report (Jan 2025)"),
    ("2025-03-07", "08:30", "Jobs report (Feb 2025)"),
    ("2025-04-04", "08:30", "Jobs report (Mar 2025)"),
    ("2025-05-02", "08:30", "Jobs report (Apr 2025)"),
    ("2025-06-06", "08:30", "Jobs report (May 2025)"),
    ("2025-07-03", "08:30", "Jobs report (Jun 2025)"),  # Thursday (Jul 4 holiday)
    ("2025-08-01", "08:30", "Jobs report (Jul 2025)"),
    ("2025-09-05", "08:30", "Jobs report (Aug 2025)"),
    ("2025-11-20", "08:30", "Jobs report (Sep 2025)"),  # delayed by shutdown (orig. 10-03); Thursday
    ("2025-12-16", "08:30", "Jobs report (Nov 2025)"),  # includes Oct 2025 data; Tuesday
]

# ── US federal election days (18:00 ET ~ approximate earliest polls close) ──
US_ELECTIONS: list[tuple[str, str, str]] = [
    ("2020-11-03", "18:00", "US election day"),
    ("2022-11-08", "18:00", "US election day"),
    ("2024-11-05", "18:00", "US election day"),
]


def all_historical_events() -> list[tuple[str, str, str, str]]:
    """Every historical event as (event_type, date, time_et, title), sorted by
    date — the same tuple shape as market_events._CALENDAR. Consumed by the
    Phase-4 strategy backtester's B6 event-window condition."""
    out = (
        [("fomc", d, t, title) for d, t, title in FOMC_DECISIONS]
        + [("cpi", d, t, title) for d, t, title in CPI_RELEASES]
        + [("nfp", d, t, title) for d, t, title in NFP_RELEASES]
        + [("election", d, t, title) for d, t, title in US_ELECTIONS]
    )
    out.sort(key=lambda e: (e[1], e[2]))
    return out


if __name__ == "__main__":
    from collections import Counter

    for name, lst in [("FOMC", FOMC_DECISIONS), ("CPI", CPI_RELEASES),
                      ("NFP", NFP_RELEASES), ("ELECTIONS", US_ELECTIONS)]:
        per_year = Counter(d[:4] for d, _, _ in lst)
        assert list(sorted(d for d, _, _ in lst)) == [d for d, _, _ in lst], name
        print(name, len(lst), dict(sorted(per_year.items())))
