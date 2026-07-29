export type Proficiency = "beginner" | "intermediate" | "advanced" | "expert";

export interface Project {
  name: string;
  summary: string;
  highlights: string[];
  technologies: string[];
  link: string | null;
}

export interface Skill {
  name: string;
  proficiency: Proficiency;
}

export interface Education {
  institution: string;
  credential: string;
  field_of_study: string;
  start_date: string;
  end_date: string;
  highlights: string[];
}

export interface WorkExperience {
  employer: string;
  title: string;
  start_date: string;
  end_date: string;
  highlights: string[];
}

export interface ProfileLink {
  label: string;
  url: string;
}

export interface WritingSample {
  title: string;
  content: string;
}

export interface ReusableStory {
  title: string;
  situation: string;
  task: string;
  action: string;
  result: string;
}

export interface CanonicalProfile {
  base_cv: string;
  projects: Project[];
  skills: Skill[];
  preferred_stack: string[];
  education: Education[];
  work_history: WorkExperience[];
  links: ProfileLink[];
  constraints: string[];
  writing_samples: WritingSample[];
  reusable_stories: ReusableStory[];
}

export interface SavedProfile {
  profile: CanonicalProfile;
  version: number;
  updated_at: string;
}

export const emptyProfile = (): CanonicalProfile => ({
  base_cv: "",
  projects: [],
  skills: [],
  preferred_stack: [],
  education: [],
  work_history: [],
  links: [],
  constraints: [],
  writing_samples: [],
  reusable_stories: [],
});
