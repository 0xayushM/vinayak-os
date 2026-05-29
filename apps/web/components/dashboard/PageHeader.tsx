interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: React.ReactNode; // optional right-side actions
}

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">{title}</h1>
        {subtitle && <p className="text-[12.5px] text-zinc-500 mt-1">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
