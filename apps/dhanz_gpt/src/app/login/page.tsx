import { connection } from "next/server";
import { authMode } from "@/lib/server/auth";
import { LoginForm } from "./login-form";

// S02 Sign in. The mode is read on the server at request time, so one build serves any sign-in mode.
export default async function LoginPage() {
  await connection();
  return <LoginForm mode={authMode()} />;
}
