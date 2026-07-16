import { ImageResponse } from "next/og";
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const alt =
  "ContactGraph — You already know someone at your next job.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OgImage(): Promise<ImageResponse> {
  const bgPath: string = join(process.cwd(), "src/app/og-bg.png");
  const bgBase64: string = readFileSync(bgPath).toString("base64");
  const bgDataUri: string = `data:image/png;base64,${bgBase64}`;

  const interBold: ArrayBuffer = await fetch(
    "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZhrib2Bg-4.ttf",
  ).then((res: Response) => res.arrayBuffer());

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          width: "100%",
          height: "100%",
          position: "relative",
        }}
      >
        <img
          src={bgDataUri}
          width={1200}
          height={630}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
        <div
          style={{
            display: "flex",
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background:
              "linear-gradient(135deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.3) 100%)",
          }}
        />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            position: "relative",
            width: "100%",
            height: "100%",
            padding: "80px",
          }}
        >
          <span
            style={{
              fontFamily: "Inter",
              fontSize: "76px",
              fontWeight: 700,
              color: "#ffffff",
              lineHeight: 1.1,
              letterSpacing: "-3px",
              maxWidth: "900px",
            }}
          >
            You already know someone at your next job.
          </span>
          <span
            style={{
              fontFamily: "Inter",
              fontSize: "44px",
              fontWeight: 700,
              color: "rgba(255,255,255,0.6)",
              marginTop: "36px",
              letterSpacing: "-1px",
            }}
          >
            ContactGraph
          </span>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        {
          name: "Inter",
          data: interBold,
          weight: 700,
          style: "normal",
        },
      ],
    },
  );
}
