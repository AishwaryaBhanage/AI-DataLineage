import { InputHTMLAttributes, LabelHTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'w-full h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-900',
        'placeholder:text-slate-400',
        'focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15',
        'transition-colors',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export function Label({
  className,
  ...props
}: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        'block mb-1.5 text-[12px] font-semibold text-slate-600 uppercase tracking-wider',
        className,
      )}
      {...props}
    />
  )
}

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-900',
      'placeholder:text-slate-400 font-mono',
      'focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15',
      'transition-colors resize-y',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'
