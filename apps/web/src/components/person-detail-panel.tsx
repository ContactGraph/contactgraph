"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { PersonDetailResult, UpdatePersonRequest } from "@/lib/api-types";
import { isRecordFormDirty } from "@/lib/detail-form-dirty";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { formatDate, formatSourceType } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";
import {
  createEmptySocialProfileEntry,
  socialProfilesFromRecord,
  socialProfilesSignature,
  socialProfilesToRecord,
  type SocialProfileEntry,
} from "@/lib/social-profiles";

interface PersonFormState {
  first_name: string;
  last_name: string;
  primary_email: string;
  phone: string;
  org_name: string;
  current_role: string;
  location: string;
  linkedin_url: string;
  bio_summary: string;
  other_profiles: SocialProfileEntry[];
}

function personToForm(person: PersonDetailResult): PersonFormState {
  return {
    first_name: person.first_name,
    last_name: person.last_name,
    primary_email: person.primary_email ?? "",
    phone: person.phone ?? "",
    org_name: person.org_name ?? "",
    current_role: person.current_role ?? "",
    location: person.location ?? "",
    linkedin_url: person.linkedin_url ?? person.social_profiles.linkedin ?? "",
    bio_summary: person.bio_summary ?? "",
    other_profiles: socialProfilesFromRecord(person.social_profiles),
  };
}

function scalarFormState(
  form: PersonFormState,
): Omit<PersonFormState, "other_profiles"> {
  const { other_profiles: _otherProfiles, ...scalar } = form;
  return scalar;
}

function buildUpdatePayload(
  personId: string,
  form: PersonFormState,
): UpdatePersonRequest {
  return {
    person_id: personId,
    first_name: form.first_name,
    last_name: form.last_name,
    primary_email: form.primary_email,
    phone: form.phone,
    org_name: form.org_name,
    current_role: form.current_role,
    location: form.location,
    linkedin_url: form.linkedin_url,
    bio_summary: form.bio_summary,
    social_profiles: socialProfilesToRecord(form.other_profiles),
  };
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) {
    return null;
  }
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 text-sm">{value}</dd>
    </div>
  );
}

export const PersonDetailPanel = forwardRef<
  EditableDetailPanelHandle,
  {
    person: PersonDetailResult;
    onDirtyChange?: (isDirty: boolean) => void;
  }
>(function PersonDetailPanel({ person, onDirtyChange }, ref) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PersonFormState>(() => personToForm(person));
  const [saved, setSaved] = useState<boolean>(false);
  const baseline: PersonFormState = useMemo(() => personToForm(person), [person]);
  const isDirty: boolean = useMemo(
    () =>
      isRecordFormDirty(scalarFormState(form), scalarFormState(baseline))
      || socialProfilesSignature(form.other_profiles)
        !== socialProfilesSignature(baseline.other_profiles),
    [form, baseline],
  );

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const saveMutation = useMutation({
    mutationFn: (payload: UpdatePersonRequest) =>
      proxyPost<PersonDetailResult>("update-person", payload),
    onSuccess: async (updated: PersonDetailResult) => {
      setForm(personToForm(updated));
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["person", person.person_id] }),
        queryClient.invalidateQueries({ queryKey: ["people"] }),
      ]);
      window.setTimeout(() => setSaved(false), 2500);
    },
  });

  useImperativeHandle(
    ref,
    () => ({
      save: async (): Promise<boolean> => {
        if (!isDirty) {
          return true;
        }
        try {
          await saveMutation.mutateAsync(
            buildUpdatePayload(person.person_id, form),
          );
          return true;
        } catch {
          return false;
        }
      },
    }),
    [form, isDirty, person.person_id, saveMutation],
  );

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    saveMutation.mutate(buildUpdatePayload(person.person_id, form));
  };

  const addProfile = (): void => {
    setForm((current) => ({
      ...current,
      other_profiles: [...current.other_profiles, createEmptySocialProfileEntry()],
    }));
  };

  const updateProfile = (
    id: string,
    field: "platform" | "url",
    value: string,
  ): void => {
    setForm((current) => ({
      ...current,
      other_profiles: current.other_profiles.map((entry) =>
        entry.id === id ? { ...entry, [field]: value } : entry,
      ),
    }));
  };

  const removeProfile = (id: string): void => {
    setForm((current) => ({
      ...current,
      other_profiles: current.other_profiles.filter((entry) => entry.id !== id),
    }));
  };

  return (
    <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          {person.is_claimed && person.avatar_url ? (
            <img
              src={person.avatar_url}
              alt=""
              className="size-10 shrink-0 rounded-full object-cover"
              referrerPolicy="no-referrer"
            />
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {person.is_claimed ? (
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-medium uppercase tracking-wide">
                Active
              </Badge>
            ) : null}
            {person.is_human ? <Badge variant="success">Human</Badge> : null}
            {person.is_broadcast ? <Badge variant="warning">Broadcast</Badge> : null}
            {person.is_automated ? <Badge variant="secondary">Automated</Badge> : null}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{person.message}</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <h3 className="text-sm font-medium">Edit contact</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="person-first-name">First name</Label>
            <Input
              id="person-first-name"
              value={form.first_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, first_name: event.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="person-last-name">Last name</Label>
            <Input
              id="person-last-name"
              value={form.last_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, last_name: event.target.value }))
              }
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-email">Primary email</Label>
          <Input
            id="person-email"
            type="email"
            value={form.primary_email}
            onChange={(event) =>
              setForm((current) => ({ ...current, primary_email: event.target.value }))
            }
          />
          {person.emails.filter(
            (email: string) =>
              email.toLowerCase() !== form.primary_email.trim().toLowerCase(),
          ).length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Other emails from imports (read-only)
              </p>
              <ul className="space-y-0.5 text-sm text-muted-foreground">
                {person.emails
                  .filter(
                    (email: string) =>
                      email.toLowerCase() !== form.primary_email.trim().toLowerCase(),
                  )
                  .map((email: string) => (
                    <li key={email}>{email}</li>
                  ))}
              </ul>
            </div>
          ) : null}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-phone">Phone</Label>
          <Input
            id="person-phone"
            value={form.phone}
            onChange={(event) =>
              setForm((current) => ({ ...current, phone: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="person-org">Organization</Label>
            {person.org_id ? (
              <Link
                href={`/graph?tab=organizations&org=${encodeURIComponent(person.org_id)}`}
                className="text-xs text-primary hover:underline"
              >
                View org →
              </Link>
            ) : null}
          </div>
          <Input
            id="person-org"
            value={form.org_name}
            onChange={(event) =>
              setForm((current) => ({ ...current, org_name: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-role">Role</Label>
          <Input
            id="person-role"
            value={form.current_role}
            onChange={(event) =>
              setForm((current) => ({ ...current, current_role: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-location">Location</Label>
          <Input
            id="person-location"
            value={form.location}
            onChange={(event) =>
              setForm((current) => ({ ...current, location: event.target.value }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="person-linkedin">LinkedIn URL</Label>
          <Input
            id="person-linkedin"
            value={form.linkedin_url}
            onChange={(event) =>
              setForm((current) => ({ ...current, linkedin_url: event.target.value }))
            }
          />
        </div>

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-medium">Other profiles</h4>
              <p className="text-xs text-muted-foreground">
                Twitter/X, Instagram, GitHub, Bluesky, and other URLs to track later.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={addProfile}>
              <Plus className="size-3.5" />
              Add
            </Button>
          </div>
          {form.other_profiles.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No other profile URLs yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {form.other_profiles.map((entry) => (
                <li
                  key={entry.id}
                  className="grid gap-2 rounded-md border p-2 sm:grid-cols-[7rem_1fr_auto]"
                >
                  <Input
                    value={entry.platform}
                    placeholder="twitter"
                    aria-label="Profile platform"
                    onChange={(event) =>
                      updateProfile(entry.id, "platform", event.target.value)
                    }
                  />
                  <Input
                    value={entry.url}
                    placeholder="https://x.com/username"
                    aria-label="Profile URL"
                    onChange={(event) =>
                      updateProfile(entry.id, "url", event.target.value)
                    }
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 shrink-0"
                    onClick={() => removeProfile(entry.id)}
                  >
                    <Trash2 className="size-3.5" />
                    <span className="sr-only">Remove profile</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="space-y-1.5">
          <Label htmlFor="person-bio">Bio</Label>
          <Textarea
            id="person-bio"
            rows={3}
            value={form.bio_summary}
            onChange={(event) =>
              setForm((current) => ({ ...current, bio_summary: event.target.value }))
            }
          />
        </div>
        {saveMutation.error ? (
          <Alert variant="destructive">
            <AlertDescription>{saveMutation.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex items-center gap-2">
          <Button
            type="submit"
            size="sm"
            disabled={!isDirty || saveMutation.isPending}
          >
            {saveMutation.isPending ? <Loader2 className="animate-spin" /> : null}
            Save changes
          </Button>
          {saved ? (
            <span className="text-xs text-muted-foreground">Saved</span>
          ) : null}
        </div>
      </form>

      <Separator />

      <dl className="grid gap-4">
        <ReadOnlyField
          label="First contact"
          value={formatDate(person.first_contact_at)}
        />
        <ReadOnlyField
          label="Last contact"
          value={formatDate(person.last_contact_at)}
        />
        <ReadOnlyField
          label="Last genuine interaction"
          value={formatDate(person.last_genuine_interaction_at)}
        />
        <ReadOnlyField
          label="Tie strength"
          value={person.tie_strength_score.toFixed(2)}
        />
        <ReadOnlyField
          label="Email count"
          value={person.email_count.toString()}
        />
      </dl>

      {person.sources.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Sources</h3>
          <div className="flex flex-wrap gap-2">
            {person.sources.map((source: string) => (
              <Badge key={source} variant="outline">
                {formatSourceType(source)}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}

      {person.inferred_categories.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Categories</h3>
          <div className="flex flex-wrap gap-2">
            {person.inferred_categories.map((category: string) => (
              <Badge key={category} variant="secondary">
                {category}
              </Badge>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
});
