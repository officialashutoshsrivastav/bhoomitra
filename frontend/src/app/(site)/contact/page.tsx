import { Hero, Section } from "@/components/ui";

export const metadata = { title: "Contact" };

export default function ContactPage() {
  return (
    <>
      <Hero title="Contact" accent="Us" subtitle="Questions about the platform, data contributions or partnerships." crumbs={[{ label: "Home", href: "/" }, { label: "Contact" }]} />
      <Section>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="card p-6">
            <h2 className="font-bold text-navy-800">Department of Land Resources</h2>
            <p className="mt-2 text-sm text-slate-700">Policy, Monitoring and Evaluation (PME) Division<br />Ministry of Rural Development, Government of India<br />NBO Building, Nirman Bhawan, New Delhi 110011</p>
            <p className="mt-3 text-sm text-slate-600">Platform support: <a className="text-brand-700 underline" href="mailto:support@bhoomitra.in">support@bhoomitra.in</a> (demo address)</p>
          </div>
          <div className="card p-6">
            <h2 className="font-bold text-navy-800">Contribute</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              <li>Researchers: create an account and upload publications for review.</li>
              <li>Data owners: register datasets with provenance and licensing.</li>
              <li>Innovators: respond to open challenges on the innovation portal.</li>
              <li>State departments: request organisation onboarding from the platform administrator.</li>
            </ul>
          </div>
        </div>
      </Section>
    </>
  );
}
