import {useCallback, useEffect, useState} from "react";

import {loadApplicationAnalytics} from "./applicationClient";
import type {AnalyticsGroupRate, AnalyticsRate, ApplicationAnalytics} from "./types";

export function ApplicationAnalyticsDashboard() {
  const [analytics, setAnalytics] = useState<ApplicationAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAnalytics(await loadApplicationAnalytics());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load application analytics.");
    }
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("application-workflow-updated", load);
    return () => window.removeEventListener("application-workflow-updated", load);
  }, [load]);

  return (
    <section className="analytics" aria-labelledby="analytics-heading">
      <div className="workflow-heading">
        <div>
          <p className="eyebrow">Recorded history only</p>
          <h1 id="analytics-heading">Application analytics</h1>
        </div>
        <p>Rates use explicit events; missing history is never treated as a negative response.</p>
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {analytics && (
        <>
          <div className="analytics-summary">
            <strong>{analytics.packets_prepared} packets prepared</strong>
            <strong>{analytics.applications_submitted} applications submitted</strong>
            <span>Review rejection rate: <strong>{formatRate(analytics.review_rejection_rate)}</strong></span>
          </div>
          <div className="analytics-grid">
            <MetricList title="Applications per day" entries={analytics.applications_per_day.map(
              (entry) => `${entry.date}: ${entry.count}`,
            )} />
            <MetricList title="Source quality" entries={analytics.source_quality.map(
              (source) => (
                `${source.source_platform}: ${source.applications} applications · `
                + `${source.responses} responses · ${source.interviews} interviews · `
                + `${source.offers} offers`
              ),
            )} />
            <MetricList title="Original score distribution" entries={analytics.score_distribution.map(
              (bucket) => `${bucket.label}: ${bucket.count}`,
            )} />
            <RateList title="Response rate by role" rates={analytics.response_rate_by_role} />
            <RateList title="Response rate by source" rates={analytics.response_rate_by_source} />
            <RateList title="Response rate by company type" rates={analytics.response_rate_by_company_type} />
            <MetricList title="Common reject reasons" entries={analytics.common_reject_reasons.map(
              (entry) => `${entry.reason}: ${entry.count}`,
            )} />
          </div>
          <details className="analytics-definitions">
            <summary>Metric definitions</summary>
            <p>{analytics.definitions.review_rejection_rate}</p>
            <p>{analytics.definitions.source_quality}</p>
            <p>{analytics.definitions.response_rate}</p>
          </details>
        </>
      )}
    </section>
  );
}

function MetricList({title, entries}: {title: string; entries: string[]}) {
  return (
    <section className="analytics-metric">
      <h2>{title}</h2>
      {entries.length ? <ul>{entries.map((entry) => <li key={entry}>{entry}</li>)}</ul> : <p>No data yet.</p>}
    </section>
  );
}

function RateList({title, rates}: {title: string; rates: AnalyticsGroupRate[]}) {
  return <MetricList title={title} entries={rates.map(
    (rate) => `${rate.group}: ${(rate.response_rate * 100).toFixed(1)}% (${rate.responses}/${rate.applications})`,
  )} />;
}

function formatRate(rate: AnalyticsRate): string {
  return rate.rate === null
    ? `Not available (${rate.numerator}/${rate.denominator})`
    : `${(rate.rate * 100).toFixed(1)}% (${rate.numerator}/${rate.denominator})`;
}
