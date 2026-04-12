import { SelectHTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      'w-full h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-900',
      'focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15',
      'transition-colors',
      className,
    )}
    {...props}
  >
    {children}
  </select>
))
Select.displayName = 'Select'
