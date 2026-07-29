import {useEffect, useState, type FormEvent, type ReactNode} from "react";

import {
  emptyProfile,
  type CanonicalProfile,
  type Proficiency,
} from "./types";

interface ProfileEditorProps {
  initialProfile: CanonicalProfile | null;
  saving: boolean;
  onSave: (profile: CanonicalProfile) => Promise<void>;
}

interface SectionProps {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}

function Section({id, title, description, children}: SectionProps) {
  return (
    <section className="profile-section" aria-labelledby={id}>
      <div className="section-heading">
        <div>
          <h2 id={id}>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function editableLines(value: string): string[] {
  return value.split("\n");
}

function editableCommas(value: string): string[] {
  return value.split(",").map((item) => item.trim());
}

function cleanList(items: string[]): string[] {
  return items.map((item) => item.trim()).filter(Boolean);
}

function cleanProfile(profile: CanonicalProfile): CanonicalProfile {
  return {
    ...profile,
    preferred_stack: cleanList(profile.preferred_stack),
    constraints: cleanList(profile.constraints),
    projects: profile.projects.map((project) => ({
      ...project,
      highlights: cleanList(project.highlights),
      technologies: cleanList(project.technologies),
    })),
    education: profile.education.map((education) => ({
      ...education,
      highlights: cleanList(education.highlights),
    })),
    work_history: profile.work_history.map((work) => ({
      ...work,
      highlights: cleanList(work.highlights),
    })),
  };
}

function removeAt<T>(items: T[], index: number): T[] {
  return items.filter((_, itemIndex) => itemIndex !== index);
}

function replaceAt<T>(items: T[], index: number, value: T): T[] {
  return items.map((item, itemIndex) => (itemIndex === index ? value : item));
}

type ProfileCollectionKey = {
  [Key in keyof CanonicalProfile]: CanonicalProfile[Key] extends unknown[] ? Key : never;
}[keyof CanonicalProfile];

type ProfileCollectionItem<Key extends ProfileCollectionKey> =
  CanonicalProfile[Key] extends Array<infer Item> ? Item : never;

function replaceProfileItem<Key extends ProfileCollectionKey>(
  profile: CanonicalProfile,
  key: Key,
  index: number,
  value: ProfileCollectionItem<Key>,
): CanonicalProfile {
  const items = profile[key] as ProfileCollectionItem<Key>[];
  return {...profile, [key]: replaceAt(items, index, value)};
}

function removeProfileItem<Key extends ProfileCollectionKey>(
  profile: CanonicalProfile,
  key: Key,
  index: number,
): CanonicalProfile {
  const items = profile[key] as ProfileCollectionItem<Key>[];
  return {...profile, [key]: removeAt(items, index)};
}

function appendProfileItem<Key extends ProfileCollectionKey>(
  profile: CanonicalProfile,
  key: Key,
  value: ProfileCollectionItem<Key>,
): CanonicalProfile {
  const items = profile[key] as ProfileCollectionItem<Key>[];
  return {...profile, [key]: [...items, value]};
}

export function ProfileEditor({initialProfile, saving, onSave}: ProfileEditorProps) {
  const [profile, setProfile] = useState<CanonicalProfile>(initialProfile ?? emptyProfile());

  useEffect(() => {
    setProfile(initialProfile ?? emptyProfile());
  }, [initialProfile]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSave(cleanProfile(profile));
  };

  const updateItem = <Key extends ProfileCollectionKey>(
    key: Key,
    index: number,
    value: ProfileCollectionItem<Key>,
  ) => {
    setProfile((current) => replaceProfileItem(current, key, index, value));
  };

  const removeItem = (key: ProfileCollectionKey, index: number) => {
    setProfile((current) => removeProfileItem(current, key, index));
  };

  const appendItem = <Key extends ProfileCollectionKey>(
    key: Key,
    value: ProfileCollectionItem<Key>,
  ) => {
    setProfile((current) => appendProfileItem(current, key, value));
  };

  return (
    <form className="profile-form" onSubmit={submit}>
      <Section
        id="base-cv"
        title="Base CV"
        description="The factual source document used when preparing role-specific drafts."
      >
        <label>
          Base CV
          <textarea
            rows={12}
            value={profile.base_cv}
            onChange={(event) =>
              setProfile((current) => ({...current, base_cv: event.target.value}))
            }
            placeholder="Paste your current CV in plain text or Markdown."
          />
        </label>
      </Section>

      <Section
        id="projects"
        title="Projects"
        description="Projects Jobinator may select or emphasize for a role."
      >
        <div className="entry-list">
          {profile.projects.map((project, index) => (
            <article className="entry-card" key={index}>
              <div className="field-grid">
                <label>
                  Name
                  <input
                    required
                    value={project.name}
                    onChange={(event) =>
                      updateItem("projects", index, {...project, name: event.target.value})
                    }
                  />
                </label>
                <label>
                  Link
                  <input
                    type="url"
                    value={project.link ?? ""}
                    onChange={(event) =>
                      updateItem("projects", index, {
                        ...project,
                        link: event.target.value || null,
                      })
                    }
                  />
                </label>
              </div>
              <label>
                Summary
                <textarea
                  rows={3}
                  value={project.summary}
                  onChange={(event) =>
                    updateItem("projects", index, {...project, summary: event.target.value})
                  }
                />
              </label>
              <label>
                Highlights <span>one per line</span>
                <textarea
                  rows={3}
                  value={project.highlights.join("\n")}
                  onChange={(event) =>
                    updateItem("projects", index, {
                      ...project,
                      highlights: editableLines(event.target.value),
                    })
                  }
                />
              </label>
              <label>
                Technologies <span>comma-separated</span>
                <input
                  value={project.technologies.join(", ")}
                  onChange={(event) =>
                    updateItem("projects", index, {
                      ...project,
                      technologies: editableCommas(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("projects", index)}
              >
                Remove project
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            appendItem("projects", {
              name: "",
              summary: "",
              highlights: [],
              technologies: [],
              link: null,
            })
          }
        >
          Add project
        </button>
      </Section>

      <Section
        id="skills"
        title="Skills"
        description="Record proficiency explicitly so matching remains honest."
      >
        <div className="entry-list compact-list">
          {profile.skills.map((skill, index) => (
            <article className="entry-card inline-card" key={index}>
              <label>
                Name
                <input
                  required
                  value={skill.name}
                  onChange={(event) =>
                    updateItem("skills", index, {...skill, name: event.target.value})
                  }
                />
              </label>
              <label>
                Proficiency
                <select
                  value={skill.proficiency}
                  onChange={(event) =>
                    updateItem("skills", index, {
                      ...skill,
                      proficiency: event.target.value as Proficiency,
                    })
                  }
                >
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                  <option value="expert">Expert</option>
                </select>
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("skills", index)}
              >
                Remove skill
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() => appendItem("skills", {name: "", proficiency: "intermediate"})}
        >
          Add skill
        </button>
      </Section>

      <Section
        id="preferred-stack"
        title="Preferred stack"
        description="Technologies and tools you want future roles to emphasize."
      >
        <label>
          Preferred stack <span>comma-separated</span>
          <input
            value={profile.preferred_stack.join(", ")}
            onChange={(event) =>
              setProfile((current) => ({
                ...current,
                preferred_stack: editableCommas(event.target.value),
              }))
            }
          />
        </label>
      </Section>

      <Section
        id="education"
        title="Education"
        description="Degrees, bootcamps, certificates, and relevant study."
      >
        <div className="entry-list">
          {profile.education.map((education, index) => (
            <article className="entry-card" key={index}>
              <div className="field-grid">
                <label>
                  Institution
                  <input
                    required
                    value={education.institution}
                    onChange={(event) =>
                      updateItem("education", index, {
                        ...education,
                        institution: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Credential
                  <input
                    value={education.credential}
                    onChange={(event) =>
                      updateItem("education", index, {
                        ...education,
                        credential: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Field of study
                  <input
                    value={education.field_of_study}
                    onChange={(event) =>
                      updateItem("education", index, {
                        ...education,
                        field_of_study: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Start date
                  <input
                    placeholder="YYYY-MM"
                    value={education.start_date}
                    onChange={(event) =>
                      updateItem("education", index, {
                        ...education,
                        start_date: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  End date
                  <input
                    placeholder="YYYY-MM or present"
                    value={education.end_date}
                    onChange={(event) =>
                      updateItem("education", index, {
                        ...education,
                        end_date: event.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <label>
                Highlights <span>one per line</span>
                <textarea
                  rows={3}
                  value={education.highlights.join("\n")}
                  onChange={(event) =>
                    updateItem("education", index, {
                      ...education,
                      highlights: editableLines(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("education", index)}
              >
                Remove education
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            appendItem("education", {
              institution: "",
              credential: "",
              field_of_study: "",
              start_date: "",
              end_date: "",
              highlights: [],
            })
          }
        >
          Add education
        </button>
      </Section>

      <Section
        id="work-history"
        title="Work history"
        description="Employment, internships, apprenticeships, and other relevant experience."
      >
        <div className="entry-list">
          {profile.work_history.map((work, index) => (
            <article className="entry-card" key={index}>
              <div className="field-grid">
                <label>
                  Employer
                  <input
                    required
                    value={work.employer}
                    onChange={(event) =>
                      updateItem("work_history", index, {
                        ...work,
                        employer: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Title
                  <input
                    required
                    value={work.title}
                    onChange={(event) =>
                      updateItem("work_history", index, {...work, title: event.target.value})
                    }
                  />
                </label>
                <label>
                  Start date
                  <input
                    placeholder="YYYY-MM"
                    value={work.start_date}
                    onChange={(event) =>
                      updateItem("work_history", index, {
                        ...work,
                        start_date: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  End date
                  <input
                    placeholder="YYYY-MM or present"
                    value={work.end_date}
                    onChange={(event) =>
                      updateItem("work_history", index, {
                        ...work,
                        end_date: event.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <label>
                Highlights <span>one per line</span>
                <textarea
                  rows={3}
                  value={work.highlights.join("\n")}
                  onChange={(event) =>
                    updateItem("work_history", index, {
                      ...work,
                      highlights: editableLines(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("work_history", index)}
              >
                Remove work entry
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            appendItem("work_history", {
              employer: "",
              title: "",
              start_date: "",
              end_date: "",
              highlights: [],
            })
          }
        >
          Add work entry
        </button>
      </Section>

      <Section
        id="links"
        title="Links"
        description="Portfolio, code, professional profiles, and other supporting material."
      >
        <div className="entry-list compact-list">
          {profile.links.map((link, index) => (
            <article className="entry-card inline-card" key={index}>
              <label>
                Label
                <input
                  required
                  value={link.label}
                  onChange={(event) =>
                    updateItem("links", index, {...link, label: event.target.value})
                  }
                />
              </label>
              <label>
                URL
                <input
                  required
                  type="url"
                  value={link.url}
                  onChange={(event) =>
                    updateItem("links", index, {...link, url: event.target.value})
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("links", index)}
              >
                Remove link
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() => appendItem("links", {label: "", url: ""})}
        >
          Add link
        </button>
      </Section>

      <Section
        id="constraints"
        title="Constraints"
        description="Location, authorization, schedule, compensation, and role constraints."
      >
        <label>
          Constraints <span>one per line</span>
          <textarea
            rows={5}
            value={profile.constraints.join("\n")}
            onChange={(event) =>
              setProfile((current) => ({
                ...current,
                constraints: editableLines(event.target.value),
              }))
            }
          />
        </label>
      </Section>

      <Section
        id="writing-samples"
        title="Writing samples"
        description="Samples that guide the voice of generated application materials."
      >
        <div className="entry-list">
          {profile.writing_samples.map((sample, index) => (
            <article className="entry-card" key={index}>
              <label>
                Title
                <input
                  required
                  value={sample.title}
                  onChange={(event) =>
                    updateItem("writing_samples", index, {
                      ...sample,
                      title: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                Content
                <textarea
                  rows={6}
                  value={sample.content}
                  onChange={(event) =>
                    updateItem("writing_samples", index, {
                      ...sample,
                      content: event.target.value,
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("writing_samples", index)}
              >
                Remove writing sample
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() => appendItem("writing_samples", {title: "", content: ""})}
        >
          Add writing sample
        </button>
      </Section>

      <Section
        id="reusable-stories"
        title="Reusable stories"
        description="Factual STAR stories to draw from for applications and interviews."
      >
        <div className="entry-list">
          {profile.reusable_stories.map((story, index) => (
            <article className="entry-card" key={index}>
              <label>
                Title
                <input
                  required
                  value={story.title}
                  onChange={(event) =>
                    updateItem("reusable_stories", index, {
                      ...story,
                      title: event.target.value,
                    })
                  }
                />
              </label>
              {(["situation", "task", "action", "result"] as const).map((field) => (
                <label key={field}>
                  {field[0].toUpperCase() + field.slice(1)}
                  <textarea
                    rows={3}
                    value={story[field]}
                    onChange={(event) =>
                      updateItem("reusable_stories", index, {
                        ...story,
                        [field]: event.target.value,
                      })
                    }
                  />
                </label>
              ))}
              <button
                className="remove-button"
                type="button"
                onClick={() => removeItem("reusable_stories", index)}
              >
                Remove story
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            appendItem("reusable_stories", {
              title: "",
              situation: "",
              task: "",
              action: "",
              result: "",
            })
          }
        >
          Add story
        </button>
      </Section>

      <div className="save-bar">
        <p>Changes stay on this device in Jobinator's local database.</p>
        <button className="save-button" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save profile"}
        </button>
      </div>
    </form>
  );
}
