"use client";
import { redirect } from "next/navigation";
export default function ApprovalsRedirect() { redirect("/app/admin?tab=approvals"); }
