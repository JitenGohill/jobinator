import {useEffect, useState} from "react";

import {ApplicationWorkflowBoard} from "./application/ApplicationWorkflowBoard";
import {ApplicationAnalyticsDashboard} from "./application/ApplicationAnalyticsDashboard";
import {DiscoveryDashboard} from "./discovery/DiscoveryDashboard";
import {ProfileEditor} from "./profile/ProfileEditor";
import {loadProfile, saveProfile} from "./profile/profileClient";
import type {CanonicalProfile, SavedProfile} from "./profile/types";

export function App() {
  const [savedProfile, setSavedProfile] = useState<SavedProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadProfile()
      .then((profile) => {
        if (active) {
          setSavedProfile(profile);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Could not load the profile.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const save = async (profile: CanonicalProfile) => {
    setSaving(true);
    setError(null);
    try {
      const result = await saveProfile(profile, savedProfile?.version ?? null);
      setSavedProfile(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the profile.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <header className="site-header">
        <a className="brand" href="/">
          Jobinator
        </a>
        <span className="local-badge">Local only</span>
      </header>
      <main>
        <ApplicationWorkflowBoard refreshKey={savedProfile?.version ?? null} />
        <ApplicationAnalyticsDashboard />
        <DiscoveryDashboard profileVersion={savedProfile?.version ?? null} />
        <div className="page-heading">
          <p className="eyebrow">Source of truth</p>
          <h1>Canonical profile</h1>
          <p>
            Keep your facts, preferences, and writing voice in one place. Future job screening
            and application packets will use this profile without silently changing it.
          </p>
          {savedProfile && (
            <p className="save-status" role="status">
              Saved version {savedProfile.version}
            </p>
          )}
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
        </div>
        {loading ? (
          <p className="loading">Loading your profile…</p>
        ) : (
          <ProfileEditor
            initialProfile={savedProfile?.profile ?? null}
            saving={saving}
            onSave={save}
          />
        )}
      </main>
    </>
  );
}
