/* @ds-bundle: {"format":3,"namespace":"MFConceptsDesignSystem_a3a656","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Tag","sourcePath":"components/core/Tag.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"d88b3d657176","components/core/Badge.jsx":"b87a0b2e3e68","components/core/Button.jsx":"7a79de5b3580","components/core/Card.jsx":"fe05531ceeb2","components/core/IconButton.jsx":"026f09afc22d","components/core/Tag.jsx":"8e4eed2cd39b","components/forms/Input.jsx":"a4bff7421977","components/forms/Switch.jsx":"967d83f35dbf","components/navigation/Tabs.jsx":"49fb1f98a83e"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.MFConceptsDesignSystem_a3a656 = window.MFConceptsDesignSystem_a3a656 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Avatar
 * A round image or initials avatar. `ring` adds the amber creative ring;
 * `status` shows a presence dot.
 */
function Avatar({
  src,
  name = '',
  size = 'md',
  ring = false,
  status = null,
  style = {},
  ...rest
}) {
  const sizes = {
    xs: 24,
    sm: 32,
    md: 44,
    lg: 60,
    xl: 88
  };
  const dim = sizes[size] || sizes.md;
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  const statusColors = {
    online: 'var(--success)',
    away: 'var(--amber-400)',
    offline: 'var(--text-subtle)'
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      position: 'relative',
      display: 'inline-flex',
      flexShrink: 0,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      width: dim,
      height: dim,
      borderRadius: '50%',
      overflow: 'hidden',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: src ? 'var(--surface-2)' : 'var(--gradient-amber)',
      color: 'var(--ink-900)',
      fontFamily: 'var(--font-display)',
      fontWeight: 700,
      fontSize: dim * 0.38,
      letterSpacing: '0.01em',
      boxShadow: ring ? '0 0 0 2px var(--bg), 0 0 0 4px var(--primary)' : 'none'
    }
  }, src ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: name,
    style: {
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }) : initials), status && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      right: 0,
      bottom: 0,
      width: Math.max(8, dim * 0.22),
      height: Math.max(8, dim * 0.22),
      borderRadius: '50%',
      background: statusColors[status] || statusColors.offline,
      boxShadow: '0 0 0 2px var(--bg)'
    }
  }));
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Badge
 * A small status pill. `dot` adds a leading status dot (live/idle states).
 * Tones map to the semantic palette.
 */
function Badge({
  children,
  tone = 'neutral',
  dot = false,
  size = 'md',
  style = {},
  ...rest
}) {
  const tones = {
    neutral: {
      bg: 'var(--surface-2)',
      fg: 'var(--text-muted)',
      dotc: 'var(--text-subtle)'
    },
    amber: {
      bg: 'var(--primary-soft)',
      fg: 'var(--amber-700)',
      dotc: 'var(--primary)'
    },
    blue: {
      bg: 'var(--accent-soft)',
      fg: 'var(--blue-700)',
      dotc: 'var(--accent)'
    },
    success: {
      bg: 'var(--success-soft)',
      fg: 'var(--success)',
      dotc: 'var(--success)'
    },
    danger: {
      bg: 'var(--danger-soft)',
      fg: 'var(--danger)',
      dotc: 'var(--danger)'
    },
    ink: {
      bg: 'var(--ink-800)',
      fg: 'var(--warm-50)',
      dotc: 'var(--blue-400)'
    }
  };
  const t = tones[tone] || tones.neutral;
  const pad = size === 'sm' ? '2px 8px' : '3px 11px';
  const fs = size === 'sm' ? 11 : 12;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: pad,
      fontFamily: 'var(--font-mono)',
      fontSize: fs,
      fontWeight: 500,
      letterSpacing: '0.04em',
      lineHeight: 1.4,
      color: t.fg,
      background: t.bg,
      borderRadius: 'var(--radius-full)',
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), dot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: '50%',
      background: t.dotc,
      flexShrink: 0
    }
  }), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Button
 * The primary action element. Amber = the "doing" / creative action,
 * blue accent = forward / tech action. Secondary and ghost recede.
 */
function Button({
  children,
  variant = 'primary',
  size = 'md',
  iconLeft = null,
  iconRight = null,
  fullWidth = false,
  disabled = false,
  type = 'button',
  onClick,
  style = {},
  ...rest
}) {
  const sizes = {
    sm: {
      padding: '0 14px',
      height: 34,
      fontSize: 13,
      gap: 7,
      radius: 'var(--radius-sm)'
    },
    md: {
      padding: '0 20px',
      height: 42,
      fontSize: 14,
      gap: 8,
      radius: 'var(--radius-md)'
    },
    lg: {
      padding: '0 28px',
      height: 52,
      fontSize: 16,
      gap: 10,
      radius: 'var(--radius-md)'
    }
  };
  const s = sizes[size] || sizes.md;
  const variants = {
    primary: {
      background: 'var(--primary)',
      color: 'var(--text-on-amber)',
      border: '1.5px solid transparent',
      boxShadow: 'var(--shadow-sm)'
    },
    accent: {
      background: 'var(--accent)',
      color: 'var(--text-on-blue)',
      border: '1.5px solid transparent',
      boxShadow: 'var(--shadow-sm)'
    },
    secondary: {
      background: 'var(--surface)',
      color: 'var(--text)',
      border: '1.5px solid var(--border-strong)',
      boxShadow: 'var(--shadow-xs)'
    },
    ghost: {
      background: 'transparent',
      color: 'var(--text)',
      border: '1.5px solid transparent',
      boxShadow: 'none'
    },
    danger: {
      background: 'var(--danger)',
      color: '#fff',
      border: '1.5px solid transparent',
      boxShadow: 'var(--shadow-sm)'
    }
  };
  const v = variants[variant] || variants.primary;
  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: s.gap,
    height: s.height,
    padding: s.padding,
    width: fullWidth ? '100%' : 'auto',
    fontFamily: 'var(--font-body)',
    fontWeight: 600,
    fontSize: s.fontSize,
    letterSpacing: '0.01em',
    lineHeight: 1,
    whiteSpace: 'nowrap',
    borderRadius: s.radius,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
    transition: 'transform var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out)',
    ...v,
    ...style
  };
  const hoverBg = {
    primary: 'var(--primary-hover)',
    accent: 'var(--accent-hover)',
    secondary: 'var(--surface-2)',
    ghost: 'var(--surface-2)',
    danger: 'var(--red-600)'
  }[variant];
  const onEnter = e => {
    if (disabled) return;
    e.currentTarget.style.background = hoverBg;
    if (variant === 'ghost') e.currentTarget.style.borderColor = 'var(--border)';
  };
  const onLeave = e => {
    if (disabled) return;
    e.currentTarget.style.background = v.background;
    if (variant === 'ghost') e.currentTarget.style.borderColor = 'transparent';
  };
  const onDown = e => {
    if (disabled) return;
    e.currentTarget.style.transform = 'translateY(1px) scale(0.99)';
  };
  const onUp = e => {
    if (disabled) return;
    e.currentTarget.style.transform = 'none';
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    disabled: disabled,
    onClick: onClick,
    style: base,
    onMouseEnter: onEnter,
    onMouseLeave: onLeave,
    onMouseDown: onDown,
    onMouseUp: onUp
  }, rest), iconLeft && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      flexShrink: 0
    }
  }, iconLeft), children, iconRight && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      flexShrink: 0
    }
  }, iconRight));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Card
 * The surface primitive. `interactive` lifts on hover. `accent` paints a
 * top hairline in amber (creative) or blue (tech). `tone="ink"` flips to the
 * dark teal-navy surface.
 */
function Card({
  children,
  interactive = false,
  accent = null,
  tone = 'default',
  padding = 'md',
  style = {},
  onClick,
  ...rest
}) {
  const pads = {
    none: 0,
    sm: 16,
    md: 24,
    lg: 32
  };
  const p = pads[padding] ?? pads.md;
  const isInk = tone === 'ink';
  const accentColor = accent === 'amber' ? 'var(--primary)' : accent === 'blue' ? 'var(--accent)' : null;
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: onClick,
    onMouseEnter: () => interactive && setHover(true),
    onMouseLeave: () => interactive && setHover(false),
    style: {
      position: 'relative',
      background: isInk ? 'var(--gradient-ink)' : 'var(--surface)',
      color: isInk ? 'var(--warm-50)' : 'var(--text)',
      border: `1px solid ${isInk ? 'var(--ink-600)' : 'var(--border)'}`,
      borderRadius: 'var(--radius-lg)',
      padding: p,
      boxShadow: interactive && hover ? 'var(--shadow-lg)' : 'var(--shadow-sm)',
      transform: interactive && hover ? 'translateY(-3px)' : 'none',
      cursor: interactive || onClick ? 'pointer' : 'default',
      transition: 'transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out), border-color var(--dur-base) var(--ease-out)',
      overflow: 'hidden',
      ...style
    }
  }, rest), accentColor && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      height: 3,
      background: accentColor
    }
  }), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — IconButton
 * A square, icon-only control for toolbars and compact UI. Pass a single
 * icon node as children (e.g. a Lucide <svg>).
 */
function IconButton({
  children,
  variant = 'ghost',
  size = 'md',
  disabled = false,
  label,
  onClick,
  style = {},
  ...rest
}) {
  const sizes = {
    sm: 32,
    md: 40,
    lg: 48
  };
  const dim = sizes[size] || sizes.md;
  const variants = {
    ghost: {
      background: 'transparent',
      color: 'var(--text-muted)',
      border: '1.5px solid transparent'
    },
    solid: {
      background: 'var(--surface)',
      color: 'var(--text)',
      border: '1.5px solid var(--border)'
    },
    primary: {
      background: 'var(--primary)',
      color: 'var(--text-on-amber)',
      border: '1.5px solid transparent'
    },
    accent: {
      background: 'var(--accent)',
      color: 'var(--text-on-blue)',
      border: '1.5px solid transparent'
    }
  };
  const v = variants[variant] || variants.ghost;
  const hover = {
    ghost: 'var(--surface-2)',
    solid: 'var(--surface-2)',
    primary: 'var(--primary-hover)',
    accent: 'var(--accent-hover)'
  }[variant];
  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: dim,
    height: dim,
    borderRadius: 'var(--radius-md)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
    transition: 'background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out)',
    ...v,
    ...style
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    disabled: disabled,
    onClick: onClick,
    style: base,
    onMouseEnter: e => {
      if (!disabled) {
        e.currentTarget.style.background = hover;
        e.currentTarget.style.color = variant === 'ghost' ? 'var(--text)' : v.color;
      }
    },
    onMouseLeave: e => {
      if (!disabled) {
        e.currentTarget.style.background = v.background;
        e.currentTarget.style.color = v.color;
      }
    },
    onMouseDown: e => {
      if (!disabled) e.currentTarget.style.transform = 'scale(0.92)';
    },
    onMouseUp: e => {
      if (!disabled) e.currentTarget.style.transform = 'none';
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Tag.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Tag
 * A bordered keyword chip (skills, filters, tech). Echoes the CV's tl-tag.
 * `warm` tints it amber (creative tags); default is cool/neutral. Optional
 * removable affordance via onRemove.
 */
function Tag({
  children,
  warm = false,
  active = false,
  onRemove,
  onClick,
  style = {},
  ...rest
}) {
  const color = warm ? 'var(--amber-700)' : 'var(--ink-600)';
  const borderC = warm ? 'color-mix(in oklch, var(--amber-500) 38%, transparent)' : 'var(--border-strong)';
  const interactive = !!onClick;
  return /*#__PURE__*/React.createElement("span", _extends({
    onClick: onClick,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      padding: '4px 11px',
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      letterSpacing: '0.04em',
      lineHeight: 1.5,
      color: active ? warm ? 'var(--amber-800)' : 'var(--accent-press)' : color,
      background: active ? warm ? 'var(--primary-soft)' : 'var(--accent-soft)' : 'transparent',
      border: `1px solid ${active ? warm ? 'var(--primary)' : 'var(--accent)' : borderC}`,
      borderRadius: 'var(--radius-sm)',
      cursor: interactive ? 'pointer' : 'default',
      transition: 'color var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)',
      ...style
    },
    onMouseEnter: e => {
      if (interactive && !active) {
        e.currentTarget.style.borderColor = warm ? 'var(--primary)' : 'var(--accent)';
        e.currentTarget.style.color = warm ? 'var(--amber-800)' : 'var(--accent)';
      }
    },
    onMouseLeave: e => {
      if (interactive && !active) {
        e.currentTarget.style.borderColor = borderC;
        e.currentTarget.style.color = color;
      }
    }
  }, rest), children, onRemove && /*#__PURE__*/React.createElement("button", {
    type: "button",
    "aria-label": "Remove",
    onClick: e => {
      e.stopPropagation();
      onRemove(e);
    },
    style: {
      display: 'inline-flex',
      border: 'none',
      background: 'none',
      padding: 0,
      margin: 0,
      cursor: 'pointer',
      color: 'inherit',
      opacity: 0.6,
      fontSize: 13,
      lineHeight: 1
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tag.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Input
 * Text field with optional label, leading icon, and helper/error text.
 * Focus shows the blue tech ring.
 */
function Input({
  label,
  value,
  onChange,
  placeholder = '',
  type = 'text',
  iconLeft = null,
  helper = '',
  error = '',
  disabled = false,
  id,
  style = {},
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const invalid = !!error;
  const borderColor = invalid ? 'var(--danger)' : focus ? 'var(--accent)' : 'var(--border-strong)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 7,
      width: '100%',
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: inputId,
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      background: disabled ? 'var(--surface-2)' : 'var(--surface)',
      border: `1.5px solid ${borderColor}`,
      borderRadius: 'var(--radius-md)',
      padding: '0 13px',
      height: 44,
      boxShadow: focus && !invalid ? 'var(--focus-ring)' : 'none',
      transition: 'border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out)',
      opacity: disabled ? 0.6 : 1
    }
  }, iconLeft && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      color: 'var(--text-subtle)',
      flexShrink: 0
    }
  }, iconLeft), /*#__PURE__*/React.createElement("input", _extends({
    id: inputId,
    type: type,
    value: value,
    onChange: onChange,
    placeholder: placeholder,
    disabled: disabled,
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      flex: 1,
      border: 'none',
      outline: 'none',
      background: 'transparent',
      fontFamily: 'var(--font-body)',
      fontSize: 15,
      color: 'var(--text)',
      height: '100%',
      minWidth: 0
    }
  }, rest))), (helper || error) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: invalid ? 'var(--danger)' : 'var(--text-muted)',
      fontFamily: 'var(--font-body)'
    }
  }, error || helper));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Switch
 * A toggle. On-state fills with the blue tech accent (or amber if
 * tone="amber"). Optional label.
 */
function Switch({
  checked = false,
  onChange,
  label,
  tone = 'blue',
  disabled = false,
  id,
  style = {},
  ...rest
}) {
  const onColor = tone === 'amber' ? 'var(--primary)' : 'var(--accent)';
  const switchId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const track = /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: "switch",
    "aria-checked": checked,
    id: switchId,
    disabled: disabled,
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      position: 'relative',
      width: 44,
      height: 26,
      flexShrink: 0,
      borderRadius: 'var(--radius-full)',
      border: 'none',
      padding: 0,
      background: checked ? onColor : 'var(--border-strong)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      transition: 'background var(--dur-base) var(--ease-out)'
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: 3,
      left: checked ? 21 : 3,
      width: 20,
      height: 20,
      borderRadius: '50%',
      background: '#fff',
      boxShadow: 'var(--shadow-sm)',
      transition: 'left var(--dur-base) var(--ease-out)'
    }
  }));
  if (!label) return track;
  return /*#__PURE__*/React.createElement("label", {
    htmlFor: switchId,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 11,
      cursor: disabled ? 'not-allowed' : 'pointer',
      ...style
    }
  }, track, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-body)',
      fontSize: 14,
      color: 'var(--text)'
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * MF Concepts — Tabs
 * An underline tab bar. The active tab is marked with an amber (creative) or
 * blue (tech) underline. Controlled via `value` + `onChange`.
 *
 * items: [{ id, label, icon? }]
 */
function Tabs({
  items = [],
  value,
  onChange,
  tone = 'amber',
  style = {},
  ...rest
}) {
  const underline = tone === 'blue' ? 'var(--accent)' : 'var(--primary)';
  const activeColor = tone === 'blue' ? 'var(--accent-press)' : 'var(--text)';
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "tablist",
    style: {
      display: 'flex',
      gap: 4,
      borderBottom: '1px solid var(--border)',
      ...style
    }
  }, rest), items.map(it => {
    const active = it.id === value;
    return /*#__PURE__*/React.createElement("button", {
      key: it.id,
      role: "tab",
      "aria-selected": active,
      onClick: () => onChange && onChange(it.id),
      style: {
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '11px 16px',
        border: 'none',
        background: 'none',
        cursor: 'pointer',
        fontFamily: 'var(--font-body)',
        fontSize: 14,
        fontWeight: active ? 600 : 500,
        color: active ? activeColor : 'var(--text-muted)',
        transition: 'color var(--dur-fast) var(--ease-out)'
      },
      onMouseEnter: e => {
        if (!active) e.currentTarget.style.color = 'var(--text)';
      },
      onMouseLeave: e => {
        if (!active) e.currentTarget.style.color = 'var(--text-muted)';
      }
    }, it.icon && /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex'
      }
    }, it.icon), it.label, /*#__PURE__*/React.createElement("span", {
      style: {
        position: 'absolute',
        left: 8,
        right: 8,
        bottom: -1,
        height: 2.5,
        borderRadius: '2px 2px 0 0',
        background: underline,
        transform: active ? 'scaleX(1)' : 'scaleX(0)',
        transformOrigin: 'center',
        transition: 'transform var(--dur-base) var(--ease-out)'
      }
    }));
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
