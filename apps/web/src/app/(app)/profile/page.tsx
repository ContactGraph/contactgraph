"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Loader2,
  LogOut,
  Pencil,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { LinkedInProfileUploadDialog } from "@/components/setup/linkedin-profile-upload-dialog";
import { FileDropZone } from "@/components/ui/file-drop-zone";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type {
  DeleteUserAccountResult,
  DeleteUserExperienceRequest,
  ListSourcesResult,
  SaveUserExperienceRequest,
  SourceType,
  UpdateUserProfileRequest,
  UploadSourceResult,
  UserExperience,
  UserProfileResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { isLinkedInProfileComplete, sourceForType } from "@/lib/setup-utils";
import {
  createEmptySocialProfileEntry,
  socialProfilesFromRecord,
  socialProfilesSignature,
  socialProfilesToRecord,
  type SocialProfileEntry,
} from "@/lib/social-profiles";

function formatDateRange(exp: UserExperience): string {
  const parts: string[] = [];
  if (exp.started_at) {
    parts.push(
      new Date(exp.started_at + "T00:00:00").toLocaleDateString(undefined, {
        month: "short",
        year: "numeric",
      }),
    );
  }
  if (exp.is_current) {
    parts.push("Present");
  } else if (exp.ended_at) {
    parts.push(
      new Date(exp.ended_at + "T00:00:00").toLocaleDateString(undefined, {
        month: "short",
        year: "numeric",
      }),
    );
  }
  return parts.join(" – ") || "";
}

interface ExperienceFormState {
  id: string | null;
  company: string;
  role: string;
  is_current: boolean;
  started_at: string;
  ended_at: string;
}

const EMPTY_FORM: ExperienceFormState = {
  id: null,
  company: "",
  role: "",
  is_current: false,
  started_at: "",
  ended_at: "",
};

export default function ProfilePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);
  const [form, setForm] = useState<ExperienceFormState>(EMPTY_FORM);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [profileSaved, setProfileSaved] = useState<boolean>(false);
  const [awaitingSync, setAwaitingSync] = useState<boolean>(false);
  const [deleteAccountDialogOpen, setDeleteAccountDialogOpen] =
    useState<boolean>(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState<boolean>(false);

  const [profileName, setProfileName] = useState<string>("");
  const [profileLocation, setProfileLocation] = useState<string>("");
  const [profilePhone, setProfilePhone] = useState<string>("");
  const [profileLinkedin, setProfileLinkedin] = useState<string>("");
  const [profileBio, setProfileBio] = useState<string>("");
  const [socialEntries, setSocialEntries] = useState<SocialProfileEntry[]>([]);
  const profileInitialized = useRef<boolean>(false);

  const profileQuery = useQuery({
    queryKey: ["user-profile"],
    queryFn: () => proxyPost<UserProfileResult>("get-user-profile"),
  });

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    refetchInterval: awaitingSync ? 2000 : false,
  });

  useEffect(() => {
    if (!awaitingSync) {
      return;
    }
    const source = sourcesQuery.data?.sources.find(
      (s) => s.source_type === "linkedin_profile_upload",
    );
    if (source === undefined) {
      return;
    }
    if (source.sync_state === "complete" || source.sync_state === "failed") {
      setAwaitingSync(false);
      if (source.sync_state === "failed") {
        setUploadError("Could not read that PDF. Try re-exporting from LinkedIn.");
      }
      profileInitialized.current = false;
      void queryClient.invalidateQueries({ queryKey: ["user-profile"] });
    }
  }, [awaitingSync, sourcesQuery.data, queryClient]);

  const profile: UserProfileResult | undefined = profileQuery.data;

  if (profile && !profileInitialized.current) {
    profileInitialized.current = true;
    setProfileName(profile.display_name ?? "");
    setProfileLocation(profile.location ?? "");
    setProfilePhone(profile.phone ?? "");
    setProfileLinkedin(profile.linkedin_url ?? "");
    setProfileBio(profile.bio_summary ?? "");
    setSocialEntries(socialProfilesFromRecord(profile.social_profiles ?? {}));
  }

  const profileMutation = useMutation({
    mutationFn: (payload: UpdateUserProfileRequest) =>
      proxyPost<UserProfileResult>("update-user-profile", payload),
    onSuccess: async () => {
      setProfileSaved(true);
      profileInitialized.current = false;
      await queryClient.invalidateQueries({ queryKey: ["user-profile"] });
      window.setTimeout(() => setProfileSaved(false), 2500);
    },
  });

  const baselineSocialSig: string = useMemo(
    () =>
      socialProfilesSignature(
        socialProfilesFromRecord(profile?.social_profiles ?? {}),
      ),
    [profile],
  );

  const isProfileDirty: boolean = useMemo(() => {
    if (!profile) return false;
    if (profileName !== (profile.display_name ?? "")) return true;
    if (profileLocation !== (profile.location ?? "")) return true;
    if (profilePhone !== (profile.phone ?? "")) return true;
    if (profileLinkedin !== (profile.linkedin_url ?? "")) return true;
    if (profileBio !== (profile.bio_summary ?? "")) return true;
    if (socialProfilesSignature(socialEntries) !== baselineSocialSig)
      return true;
    return false;
  }, [
    profile,
    profileName,
    profileLocation,
    profilePhone,
    profileLinkedin,
    profileBio,
    socialEntries,
    baselineSocialSig,
  ]);

  const addSocialProfile = useCallback((): void => {
    setSocialEntries((prev) => [...prev, createEmptySocialProfileEntry()]);
  }, []);

  const updateSocialProfile = useCallback(
    (id: string, field: "platform" | "url", value: string): void => {
      setSocialEntries((prev) =>
        prev.map((e) => (e.id === id ? { ...e, [field]: value } : e)),
      );
    },
    [],
  );

  const removeSocialProfile = useCallback((id: string): void => {
    setSocialEntries((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const saveMutation = useMutation({
    mutationFn: (payload: SaveUserExperienceRequest) =>
      proxyPost<UserProfileResult>("save-user-experience", payload),
    onSuccess: async () => {
      setDialogOpen(false);
      setForm(EMPTY_FORM);
      profileInitialized.current = false;
      await queryClient.invalidateQueries({ queryKey: ["user-profile"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (payload: DeleteUserExperienceRequest) =>
      proxyPost<UserProfileResult>("delete-user-experience", payload),
    onSuccess: async () => {
      profileInitialized.current = false;
      await queryClient.invalidateQueries({ queryKey: ["user-profile"] });
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: () => proxyPost<DeleteUserAccountResult>("delete-user-account"),
    onSuccess: async (result: DeleteUserAccountResult) => {
      if (!result.deleted) {
        return;
      }
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/");
      router.refresh();
    },
  });

  const handleSignOut = useCallback(async (): Promise<void> => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/");
    router.refresh();
  }, [router]);

  const uploadMutation = useMutation({
    mutationFn: (payload: {
      source_type: SourceType;
      filename: string;
      content: string;
    }) => proxyPost<UploadSourceResult>("upload-source", payload),
    onSuccess: async () => {
      setUploadError(null);
      setAwaitingSync(true);
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (error: Error) => {
      setUploadError(error.message);
    },
  });

  const handlePdfUpload = useCallback(
    async (file: File): Promise<void> => {
      const buffer: ArrayBuffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      for (const byte of bytes) {
        binary += String.fromCharCode(byte);
      }
      const base64: string = btoa(binary);
      uploadMutation.mutate({
        source_type: "linkedin_profile_upload",
        filename: file.name,
        content: base64,
      });
    },
    [uploadMutation],
  );

  const sources = sourcesQuery.data?.sources ?? [];
  const linkedinProfileSource = sourceForType(sources, "linkedin_profile_upload");
  const linkedinProfileComplete: boolean = isLinkedInProfileComplete(sources);
  const linkedinProfileBusy: boolean =
    uploadMutation.isPending || awaitingSync;

  const openEditDialog = useCallback((exp: UserExperience): void => {
    setForm({
      id: exp.id,
      company: exp.company,
      role: exp.role ?? "",
      is_current: exp.is_current,
      started_at: exp.started_at ?? "",
      ended_at: exp.ended_at ?? "",
    });
    setDialogOpen(true);
  }, []);

  const openNewDialog = useCallback((): void => {
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }, []);

  const handleSave = useCallback((): void => {
    if (!form.company.trim()) {
      return;
    }
    saveMutation.mutate({
      id: form.id,
      company: form.company.trim(),
      role: form.role.trim() || null,
      is_current: form.is_current,
      started_at: form.started_at || null,
      ended_at: form.is_current ? null : form.ended_at || null,
    });
  }, [form, saveMutation]);

  const experiences: UserExperience[] = profile?.experiences ?? [];

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Your Profile</h1>
          <p className="text-muted-foreground">
            Your professional background helps identify the right version of your
            contacts during enrichment.
          </p>
        </div>
        {linkedinProfileComplete ? (
          <Button
            variant="outline"
            size="sm"
            className="shrink-0"
            disabled={linkedinProfileBusy}
            onClick={() => setUploadDialogOpen(true)}
          >
            {linkedinProfileBusy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Upload className="size-4" />
            )}
            Re-upload
          </Button>
        ) : null}
      </div>

      {!linkedinProfileComplete ? (
        <>
          <FileDropZone
            accept=".pdf,application/pdf"
            onFileSelect={(file: File) => void handlePdfUpload(file)}
            disabled={linkedinProfileBusy}
            busy={linkedinProfileBusy}
            busyMessage={awaitingSync ? "Processing PDF…" : "Uploading…"}
            idleMessage="Drag and drop your LinkedIn PDF here"
            idleHint="or click to choose a file"
          />

          {uploadError ? (
            <Alert variant="destructive">
              <AlertDescription>{uploadError}</AlertDescription>
            </Alert>
          ) : null}
        </>
      ) : null}

      {/* Basic info */}
      <Card>
        <CardHeader>
          <CardTitle>Basic info</CardTitle>
          <CardDescription>
            Email comes from Google sign-in. Edit anything else below.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {profileQuery.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="profile-email">Email</Label>
                  <Input
                    id="profile-email"
                    value={profile?.email ?? ""}
                    readOnly
                    disabled
                    className="bg-muted"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-name">Name</Label>
                  <Input
                    id="profile-name"
                    placeholder="Your name"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                  />
                </div>
                {profile?.headline ? (
                  <div className="space-y-2 sm:col-span-2">
                    <Label>Headline</Label>
                    <p className="text-sm text-muted-foreground">
                      {profile.headline}
                    </p>
                  </div>
                ) : null}
                <div className="space-y-2">
                  <Label htmlFor="profile-phone">Phone</Label>
                  <Input
                    id="profile-phone"
                    placeholder="+1 555-123-4567"
                    value={profilePhone}
                    onChange={(e) => setProfilePhone(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-location">Location</Label>
                  <Input
                    id="profile-location"
                    placeholder="San Francisco, CA"
                    value={profileLocation}
                    onChange={(e) => setProfileLocation(e.target.value)}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="profile-linkedin">LinkedIn URL</Label>
                  <Input
                    id="profile-linkedin"
                    placeholder="https://linkedin.com/in/yourname"
                    value={profileLinkedin}
                    onChange={(e) => setProfileLinkedin(e.target.value)}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="profile-bio">Bio</Label>
                  <Textarea
                    id="profile-bio"
                    placeholder="A short bio or summary"
                    rows={3}
                    value={profileBio}
                    onChange={(e) => setProfileBio(e.target.value)}
                  />
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>Other profiles</Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={addSocialProfile}
                  >
                    <Plus className="size-4" />
                    Add
                  </Button>
                </div>
                {socialEntries.map((entry) => (
                  <div key={entry.id} className="flex items-center gap-2">
                    <Input
                      className="w-32 shrink-0"
                      placeholder="Platform"
                      value={entry.platform}
                      onChange={(e) =>
                        updateSocialProfile(entry.id, "platform", e.target.value)
                      }
                    />
                    <Input
                      className="flex-1"
                      placeholder="https://…"
                      value={entry.url}
                      onChange={(e) =>
                        updateSocialProfile(entry.id, "url", e.target.value)
                      }
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 shrink-0"
                      onClick={() => removeSocialProfile(entry.id)}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                {socialEntries.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No social profiles yet.
                  </p>
                ) : null}
              </div>

              <Separator />

              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={profileMutation.isPending || !isProfileDirty}
                  onClick={() =>
                    profileMutation.mutate({
                      display_name: profileName.trim(),
                      location: profileLocation.trim(),
                      phone: profilePhone.trim() || null,
                      linkedin_url: profileLinkedin.trim() || null,
                      bio_summary: profileBio.trim() || null,
                      social_profiles: socialProfilesToRecord(socialEntries),
                    })
                  }
                >
                  {profileMutation.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : null}
                  Save Changes
                </Button>
                {profileSaved ? (
                  <span className="text-sm text-muted-foreground">Saved</span>
                ) : null}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Work experience */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>Work experience</CardTitle>
            <CardDescription>
              Your employment history — used as context when enriching contacts.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={openNewDialog}>
            <Plus className="size-4" />
            Add
          </Button>
        </CardHeader>
        <CardContent>
          {profileQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : experiences.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No experiences yet. Upload your LinkedIn PDF or add manually.
            </p>
          ) : (
            <ul className="divide-y">
              {experiences.map((exp) => (
                <li
                  key={exp.id ?? `${exp.company}-${exp.role}`}
                  className="flex items-start justify-between gap-4 py-4"
                >
                  <div className="flex gap-3">
                    <Briefcase className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
                    <div className="space-y-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{exp.company}</p>
                        {exp.is_current ? (
                          <Badge variant="secondary">Current</Badge>
                        ) : null}
                      </div>
                      {exp.role ? (
                        <p className="text-sm text-muted-foreground">
                          {exp.role}
                        </p>
                      ) : null}
                      {formatDateRange(exp) ? (
                        <p className="text-xs text-muted-foreground">
                          {formatDateRange(exp)}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => openEditDialog(exp)}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 text-destructive"
                      disabled={deleteMutation.isPending}
                      onClick={() => {
                        if (exp.id) {
                          deleteMutation.mutate({ id: exp.id });
                        }
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Account */}
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>
            Sign out or permanently delete your account and all imported data.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button variant="outline" size="sm" onClick={() => void handleSignOut()}>
            <LogOut className="size-4" />
            Sign out
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setDeleteAccountDialogOpen(true)}
            disabled={deleteAccountMutation.isPending}
          >
            {deleteAccountMutation.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Trash2 className="size-4" />
            )}
            Delete my account
          </Button>
        </CardContent>
      </Card>

      {/* Experience dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {form.id ? "Edit experience" : "Add experience"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="exp-company">Company</Label>
              <Input
                id="exp-company"
                placeholder="Acme Corp"
                value={form.company}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, company: e.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="exp-role">Role</Label>
              <Input
                id="exp-role"
                placeholder="Software Engineer"
                value={form.role}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, role: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="exp-start">Start date</Label>
                <Input
                  id="exp-start"
                  type="date"
                  value={form.started_at}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, started_at: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="exp-end">End date</Label>
                <Input
                  id="exp-end"
                  type="date"
                  value={form.ended_at}
                  disabled={form.is_current}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, ended_at: e.target.value }))
                  }
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_current}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    is_current: e.target.checked,
                    ended_at: e.target.checked ? "" : prev.ended_at,
                  }))
                }
              />
              I currently work here
            </label>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={saveMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!form.company.trim() || saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LinkedInProfileUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onFileSelect={(file: File) => {
          void handlePdfUpload(file);
        }}
        isPending={uploadMutation.isPending}
        isProcessing={awaitingSync}
        error={uploadError}
        isComplete={linkedinProfileSource?.sync_state === "complete"}
      />

      <Dialog open={deleteAccountDialogOpen} onOpenChange={setDeleteAccountDialogOpen}>
        <DialogContent className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              This permanently deletes your account, imports, lists, job preferences,
              and network observations. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteAccountMutation.error ? (
            <Alert variant="destructive">
              <AlertDescription>{deleteAccountMutation.error.message}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteAccountDialogOpen(false)}
              disabled={deleteAccountMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteAccountMutation.isPending}
              onClick={() => deleteAccountMutation.mutate()}
            >
              {deleteAccountMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Delete my account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
