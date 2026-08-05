import {useState} from "react";

import type {
  DiscoveryLink,
  DiscoveryLinkSource,
  DiscoveryLinkSubmission,
} from "./types";

interface DiscoveryLinkIntakeProps {
  links: DiscoveryLink[];
  sourceOptions: DiscoveryLinkSource[];
  submitting: boolean;
  onSubmit: (links: DiscoveryLinkSubmission[]) => Promise<boolean>;
}

export function DiscoveryLinkIntake({
  links,
  sourceOptions,
  submitting,
  onSubmit,
}: DiscoveryLinkIntakeProps) {
  const [value, setValue] = useState("");
  const [selectedSources, setSelectedSources] = useState<Record<string, string>>({});
  const pendingUrls = value
    .split(/\r?\n/)
    .map((url) => url.trim())
    .filter((url, index, urls) => Boolean(url) && urls.indexOf(url) === index);

  const submit = async () => {
    const succeeded = await onSubmit(
      pendingUrls.map((url) => ({
        url,
        source_platform: selectedSources[url] ?? "engineering-list",
      })),
    );
    if (succeeded) {
      setValue("");
      setSelectedSources({});
    }
  };

  return (
    <section className="discovery-link-intake" aria-labelledby="link-intake-heading">
      <div>
        <p className="eyebrow">Curated sources</p>
        <h2 id="link-intake-heading">Add discovery links</h2>
        <p>
          Paste one link per line, then confirm where each listing came from.
        </p>
      </div>
      <label htmlFor="discovery-links">Discovery links</label>
      <textarea
        id="discovery-links"
        rows={4}
        value={value}
        placeholder="https://www.linkedin.com/jobs/view/…"
        onChange={(event) => setValue(event.target.value)}
      />
      {pendingUrls.length > 0 && (
        <div className="link-source-confirmations">
          {pendingUrls.map((url) => (
            <label key={url}>
              <span>Source for {url}</span>
              <select
                aria-label={`Source for ${url}`}
                value={selectedSources[url] ?? "engineering-list"}
                onChange={(event) =>
                  setSelectedSources((current) => ({
                    ...current,
                    [url]: event.target.value,
                  }))
                }
              >
                {sourceOptions.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      <button
        type="button"
        disabled={submitting || pendingUrls.length === 0}
        onClick={() => void submit()}
      >
        {submitting ? "Adding links…" : "Add discovery links"}
      </button>
      {links.length > 0 && (
        <div className="discovery-link-results">
          <h3>Discovery-link review</h3>
          {links.map((link) => (
            <article key={link.id} className={`discovery-link-${link.status}`}>
              <p>
                <strong>{link.source_platform}</strong> · {link.status}
              </p>
              {link.reason && <p>{link.reason}</p>}
              <a href={link.url} target="_blank" rel="noreferrer">
                {link.status === "unresolved" ? "Review manually" : "Open source link"}
              </a>
              {link.resolved_url && (
                <a href={link.resolved_url} target="_blank" rel="noreferrer">
                  Open resolved posting
                </a>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
