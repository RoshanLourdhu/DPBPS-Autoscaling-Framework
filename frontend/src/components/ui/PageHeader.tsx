// src/components/ui/PageHeader.tsx
import React from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle }) => (
  <header className="mb-6">
    <h1 className="text-2xl font-semibold text-gray-200">{title}</h1>
    {subtitle && <p className="text-sm text-gray-400">{subtitle}</p>}
  </header>
);
