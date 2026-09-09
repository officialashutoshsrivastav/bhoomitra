"use client";
import { redirect } from "next/navigation";
export default function JobsRedirect() { redirect("/app/admin?tab=jobs"); }
