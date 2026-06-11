"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Children, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  EditTrustedUsersResult,
  ViewTrustedUsersResult,
} from "@/lib/api-types";
import { formatDate } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

export default function SharingPage() {
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState<string>("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [inviteCopy, setInviteCopy] = useState<string | null>(null);

  const trustQuery = useQuery({
    queryKey: ["trust-list"],
    queryFn: () => proxyPost<ViewTrustedUsersResult>("view-trusted-users"),
  });

  const editMutation = useMutation({
    mutationFn: (body: Record<string, string[] | undefined>) =>
      proxyPost<EditTrustedUsersResult>("edit-trusted-users", body),
    onSuccess: async (result: EditTrustedUsersResult) => {
      setActionMessage(result.message);
      if (result.invite_copy) {
        setInviteCopy(result.invite_copy);
      }
      await queryClient.invalidateQueries({ queryKey: ["trust-list"] });
    },
    onError: (error: Error) => {
      setActionMessage(error.message);
    },
  });

  const data: ViewTrustedUsersResult | undefined = trustQuery.data;

  const handleInvite = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const email: string = inviteEmail.trim();
    if (!email) {
      return;
    }
    editMutation.mutate({ add: [email] });
    setInviteEmail("");
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Network Sharing
        </h1>
        <p className="text-muted-foreground">
          Share your professional network with trusted friends and colleagues.
          Sharing is mutual &mdash; both sides can see each other&rsquo;s
          contacts (names and roles only, no emails or phone numbers).
        </p>
      </div>

      {actionMessage ? (
        <Alert>
          <AlertDescription>{actionMessage}</AlertDescription>
        </Alert>
      ) : null}

      {inviteCopy ? (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-base">
              Share this with your friend
            </CardTitle>
            <CardDescription>
              Copy the message below and send it to them via text, email, or
              however you prefer.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-md border bg-background p-3 text-sm whitespace-pre-wrap">
              {inviteCopy}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                void navigator.clipboard.writeText(inviteCopy);
                setActionMessage("Copied to clipboard!");
              }}
            >
              Copy to clipboard
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Invite someone</CardTitle>
          <CardDescription>
            Enter their email to create an invite. We&rsquo;ll give you a
            message to forward to them &mdash; no email is sent automatically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={handleInvite}
          >
            <div className="flex-1 space-y-2">
              <Label htmlFor="invite-email">Email</Label>
              <Input
                id="invite-email"
                type="email"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="friend@example.com"
              />
            </div>
            <Button type="submit" disabled={editMutation.isPending}>
              Invite
            </Button>
          </form>
        </CardContent>
      </Card>

      {trustQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <SharingSection
            title="Shared with"
            description={`${data?.members.length ?? 0} active connections`}
            empty="You haven't shared your network with anyone yet."
          >
            {data?.members.map((member) => (
              <li
                key={member.membership_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">
                    {member.name ?? member.email}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {member.email} &middot; since{" "}
                    {formatDate(member.established_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{member.status}</Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      editMutation.mutate({ remove: [member.email] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </SharingSection>

          <SharingSection
            title="Inbound invites"
            description="Requests waiting for your response"
            empty="No pending inbound invites."
          >
            {data?.inbound_invites.map((invite) => (
              <li
                key={invite.invite_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">
                    {invite.inviter_name ?? invite.inviter_email}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {invite.inviter_email} &middot;{" "}
                    {formatDate(invite.created_at)}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      editMutation.mutate({ accept: [invite.invite_id] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Accept
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      editMutation.mutate({ decline: [invite.invite_id] })
                    }
                    disabled={editMutation.isPending}
                  >
                    Decline
                  </Button>
                </div>
              </li>
            ))}
          </SharingSection>

          <SharingSection
            title="Outbound invites"
            description="Invites you have sent"
            empty="No outbound invites."
            className="lg:col-span-2"
          >
            {data?.outbound_invites.map((invite) => (
              <li
                key={invite.invite_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">{invite.invitee_email}</p>
                  <p className="text-sm text-muted-foreground">
                    Sent {formatDate(invite.created_at)}
                  </p>
                </div>
                <Badge variant="outline">{invite.status}</Badge>
              </li>
            ))}
          </SharingSection>
        </div>
      )}
    </div>
  );
}

function SharingSection({
  title,
  description,
  empty,
  className,
  children,
}: {
  title: string;
  description: string;
  empty: string;
  className?: string;
  children: React.ReactNode;
}) {
  const hasItems: boolean = Children.count(children) > 0;

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {hasItems ? (
          <ul className="divide-y">{children}</ul>
        ) : (
          <p className="text-sm text-muted-foreground">{empty}</p>
        )}
      </CardContent>
    </Card>
  );
}
