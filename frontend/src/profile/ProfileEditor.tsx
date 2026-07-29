import {useEffect, useState, type FormEvent, type ReactNode} from "react";

import {
  emptyProfile,
  type CanonicalProfile,
  type Education,
  type ProfileLink,
  type Project,
  type Proficiency,
  type ReusableStory,
  type Skill,
  type WorkExperience,
  type WritingSample,
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

export function ProfileEditor({initialProfile, saving, onSave}: ProfileEditorProps) {
  const [profile, setProfile] = useState<CanonicalProfile>(initialProfile ?? emptyProfile());

  useEffect(() => {
    setProfile(initialProfile ?? emptyProfile());
  }, [initialProfile]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSave(cleanProfile(profile));
  };

  const updateProject = (index: number, project: Project) => {
    setProfile((current) => ({
      ...current,
      projects: replaceAt(current.projects, index, project),
    }));
  };

  const updateSkill = (index: number, skill: Skill) => {
    setProfile((current) => ({
      ...current,
      skills: replaceAt(current.skills, index, skill),
    }));
  };

  const updateEducation = (index: number, education: Education) => {
    setProfile((current) => ({
      ...current,
      education: replaceAt(current.education, index, education),
    }));
  };

  const updateWork = (index: number, work: WorkExperience) => {
    setProfile((current) => ({
      ...current,
      work_history: replaceAt(current.work_history, index, work),
    }));
  };

  const updateLink = (index: number, link: ProfileLink) => {
    setProfile((current) => ({
      ...current,
      links: replaceAt(current.links, index, link),
    }));
  };

  const updateWritingSample = (index: number, sample: WritingSample) => {
    setProfile((current) => ({
      ...current,
      writing_samples: replaceAt(current.writing_samples, index, sample),
    }));
  };

  const updateStory = (index: number, story: ReusableStory) => {
    setProfile((current) => ({
      ...current,
      reusable_stories: replaceAt(current.reusable_stories, index, story),
    }));
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
                      updateProject(index, {...project, name: event.target.value})
                    }
                  />
                </label>
                <label>
                  Link
                  <input
                    type="url"
                    value={project.link ?? ""}
                    onChange={(event) =>
                      updateProject(index, {...project, link: event.target.value || null})
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
                    updateProject(index, {...project, summary: event.target.value})
                  }
                />
              </label>
              <label>
                Highlights <span>one per line</span>
                <textarea
                  rows={3}
                  value={project.highlights.join("\n")}
                  onChange={(event) =>
                    updateProject(index, {
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
                    updateProject(index, {
                      ...project,
                      technologies: editableCommas(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    projects: removeAt(current.projects, index),
                  }))
                }
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
            setProfile((current) => ({
              ...current,
              projects: [
                ...current.projects,
                {name: "", summary: "", highlights: [], technologies: [], link: null},
              ],
            }))
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
                  onChange={(event) => updateSkill(index, {...skill, name: event.target.value})}
                />
              </label>
              <label>
                Proficiency
                <select
                  value={skill.proficiency}
                  onChange={(event) =>
                    updateSkill(index, {
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
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    skills: removeAt(current.skills, index),
                  }))
                }
              >
                Remove skill
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            setProfile((current) => ({
              ...current,
              skills: [...current.skills, {name: "", proficiency: "intermediate"}],
            }))
          }
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
                      updateEducation(index, {...education, institution: event.target.value})
                    }
                  />
                </label>
                <label>
                  Credential
                  <input
                    value={education.credential}
                    onChange={(event) =>
                      updateEducation(index, {...education, credential: event.target.value})
                    }
                  />
                </label>
                <label>
                  Field of study
                  <input
                    value={education.field_of_study}
                    onChange={(event) =>
                      updateEducation(index, {...education, field_of_study: event.target.value})
                    }
                  />
                </label>
                <label>
                  Start date
                  <input
                    placeholder="YYYY-MM"
                    value={education.start_date}
                    onChange={(event) =>
                      updateEducation(index, {...education, start_date: event.target.value})
                    }
                  />
                </label>
                <label>
                  End date
                  <input
                    placeholder="YYYY-MM or present"
                    value={education.end_date}
                    onChange={(event) =>
                      updateEducation(index, {...education, end_date: event.target.value})
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
                    updateEducation(index, {
                      ...education,
                      highlights: editableLines(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    education: removeAt(current.education, index),
                  }))
                }
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
            setProfile((current) => ({
              ...current,
              education: [
                ...current.education,
                {
                  institution: "",
                  credential: "",
                  field_of_study: "",
                  start_date: "",
                  end_date: "",
                  highlights: [],
                },
              ],
            }))
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
                    onChange={(event) => updateWork(index, {...work, employer: event.target.value})}
                  />
                </label>
                <label>
                  Title
                  <input
                    required
                    value={work.title}
                    onChange={(event) => updateWork(index, {...work, title: event.target.value})}
                  />
                </label>
                <label>
                  Start date
                  <input
                    placeholder="YYYY-MM"
                    value={work.start_date}
                    onChange={(event) => updateWork(index, {...work, start_date: event.target.value})}
                  />
                </label>
                <label>
                  End date
                  <input
                    placeholder="YYYY-MM or present"
                    value={work.end_date}
                    onChange={(event) => updateWork(index, {...work, end_date: event.target.value})}
                  />
                </label>
              </div>
              <label>
                Highlights <span>one per line</span>
                <textarea
                  rows={3}
                  value={work.highlights.join("\n")}
                  onChange={(event) =>
                    updateWork(index, {
                      ...work,
                      highlights: editableLines(event.target.value),
                    })
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    work_history: removeAt(current.work_history, index),
                  }))
                }
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
            setProfile((current) => ({
              ...current,
              work_history: [
                ...current.work_history,
                {employer: "", title: "", start_date: "", end_date: "", highlights: []},
              ],
            }))
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
                  onChange={(event) => updateLink(index, {...link, label: event.target.value})}
                />
              </label>
              <label>
                URL
                <input
                  required
                  type="url"
                  value={link.url}
                  onChange={(event) => updateLink(index, {...link, url: event.target.value})}
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    links: removeAt(current.links, index),
                  }))
                }
              >
                Remove link
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            setProfile((current) => ({
              ...current,
              links: [...current.links, {label: "", url: ""}],
            }))
          }
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
                    updateWritingSample(index, {...sample, title: event.target.value})
                  }
                />
              </label>
              <label>
                Content
                <textarea
                  rows={6}
                  value={sample.content}
                  onChange={(event) =>
                    updateWritingSample(index, {...sample, content: event.target.value})
                  }
                />
              </label>
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    writing_samples: removeAt(current.writing_samples, index),
                  }))
                }
              >
                Remove writing sample
              </button>
            </article>
          ))}
        </div>
        <button
          className="add-button"
          type="button"
          onClick={() =>
            setProfile((current) => ({
              ...current,
              writing_samples: [...current.writing_samples, {title: "", content: ""}],
            }))
          }
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
                  onChange={(event) => updateStory(index, {...story, title: event.target.value})}
                />
              </label>
              {(["situation", "task", "action", "result"] as const).map((field) => (
                <label key={field}>
                  {field[0].toUpperCase() + field.slice(1)}
                  <textarea
                    rows={3}
                    value={story[field]}
                    onChange={(event) => updateStory(index, {...story, [field]: event.target.value})}
                  />
                </label>
              ))}
              <button
                className="remove-button"
                type="button"
                onClick={() =>
                  setProfile((current) => ({
                    ...current,
                    reusable_stories: removeAt(current.reusable_stories, index),
                  }))
                }
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
            setProfile((current) => ({
              ...current,
              reusable_stories: [
                ...current.reusable_stories,
                {title: "", situation: "", task: "", action: "", result: ""},
              ],
            }))
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
