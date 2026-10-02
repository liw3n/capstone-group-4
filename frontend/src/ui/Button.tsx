import { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'link' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

/**
 * Orange is the primary call to action, blue carries links and secondary
 * actions. The reference screenshots mix the two on the pipeline empty state;
 * this standardises on orange-primary throughout.
 */
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-white hover:bg-accent-hover disabled:bg-gray-200 disabled:text-gray-400',
  secondary:
    'bg-white text-body border border-line hover:bg-gray-50 disabled:text-gray-300',
  link: 'text-link hover:text-link-hover hover:underline disabled:text-gray-300',
  ghost: 'text-accent hover:bg-accent-soft disabled:text-gray-300',
  danger: 'text-danger hover:bg-danger-soft',
};

export default function Button({
  variant = 'secondary',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const isText = variant === 'link' || variant === 'ghost' || variant === 'danger';
  const layout = isText
    ? 'px-2 py-1.5'
    : 'px-3.5 py-2 rounded-md shadow-sm';

  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed ${layout} ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </button>
  );
}
