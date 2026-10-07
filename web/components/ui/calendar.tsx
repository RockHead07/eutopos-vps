"use client"

import * as React from "react"
import { cn } from "cn"
import {
  DayPicker,
  getDefaultClassNames,
  type DayButton,
  type Locale,
} from "react-day-picker"

import { Button, buttonVariants } from "@/components/ui/button"
import { ChevronLeftIcon, ChevronRightIcon, ChevronDownIcon } from "lucide-react"

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  captionLayout = "label",
  buttonVariant = "ghost",
  locale,
  formatters,
  components,
  ...props
}: React.ComponentProps<typeof DayPicker> & {
  buttonVariant?: React.ComponentProps<typeof Button>["variant"]
}) {
  const defaultClassNames = getDefaultClassNames()

  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn(
        "group/calendar bg-background p-2 [--cell-radius:var(--radius-md)] [--cell-size:--spacing(7)] in-data-[slot=card-content]:bg-transparent in-data-[slot=popover-content]:bg-transparent",
        String.raw`rtl:**:[.rdp-button\_next>svg]:rotate-180`,
        String.raw`rtl:**:[.rdp-button\_previous>svg]:rotate-180`,
        className
      )}
      captionLayout={captionLayout}
      locale={locale}
      formatters={{
        formatWeekdayName: (date) =>
          date.toLocaleDateString("en-US", { weekday: "narrow" }),
        formatCaption: (date) =>
          date.toLocaleDateString("en-US", { month: "long", year: "numeric" }),
        formatMonthDropdown: (date) =>
          date.toLocaleString(locale?.code, { month: "short" }),
        ...formatters,
      }}
      classNames={{
        root: cn("w-fit", defaultClassNames.root),
        months: cn(
          "relative flex flex-col gap-4 md:flex-row",
          defaultClassNames.months
        ),
        month: cn("flex w-full flex-col gap-3", defaultClassNames.month),
        nav: cn(
          "absolute right-1 top-0 flex items-center gap-1 z-20",
          defaultClassNames.nav
        ),
        button_previous: cn(
          "size-8 p-0 rounded-full hover:bg-mist text-foreground inline-flex items-center justify-center cursor-pointer select-none disabled:opacity-30",
          defaultClassNames.button_previous
        ),
        button_next: cn(
          "size-8 p-0 rounded-full hover:bg-mist text-foreground inline-flex items-center justify-center cursor-pointer select-none disabled:opacity-30",
          defaultClassNames.button_next
        ),
        month_caption: cn(
          "flex h-8 w-full items-center justify-start px-1 text-base font-semibold text-foreground select-none",
          defaultClassNames.month_caption
        ),
        dropdowns: cn(
          "flex h-(--cell-size) w-full items-center justify-center gap-1.5 text-sm font-medium",
          defaultClassNames.dropdowns
        ),
        dropdown_root: cn(
          "relative rounded-(--cell-radius)",
          defaultClassNames.dropdown_root
        ),
        dropdown: cn(
          "absolute inset-0 bg-popover opacity-0",
          defaultClassNames.dropdown
        ),
        caption_label: cn(
          "text-base font-semibold text-foreground select-none",
          defaultClassNames.caption_label
        ),
        month_grid: cn("w-full border-collapse touch-none select-none", defaultClassNames.month_grid),
        weekdays: cn("flex w-full", defaultClassNames.weekdays),
        weekday: cn(
          "size-10 flex items-center justify-center text-xs font-medium text-muted-foreground select-none",
          defaultClassNames.weekday
        ),
        week: cn("flex w-full", defaultClassNames.week),
        week_number_header: cn(
          "w-10 select-none",
          defaultClassNames.week_number_header
        ),
        week_number: cn(
          "text-[0.8rem] text-muted-foreground select-none",
          defaultClassNames.week_number
        ),
        day: cn(
          "group/day relative size-10 p-0 text-center select-none touch-none",
          defaultClassNames.day
        ),
        range_start: cn("p-0", defaultClassNames.range_start),
        range_middle: cn("p-0", defaultClassNames.range_middle),
        range_end: cn("p-0", defaultClassNames.range_end),
        today: cn(
          "[&:not([data-selected=true])_button]:ring-1 [&:not([data-selected=true])_button]:ring-forest/60 [&:not([data-selected=true])_button]:text-forest font-semibold",
          defaultClassNames.today
        ),
        outside: cn(
          "text-muted-foreground/40 opacity-40",
          defaultClassNames.outside
        ),
        disabled: cn(
          "text-muted-foreground/30 opacity-30 pointer-events-none cursor-not-allowed",
          defaultClassNames.disabled
        ),
        hidden: cn("invisible", defaultClassNames.hidden),
        ...classNames,
      }}
      components={{
        Root: ({ className, rootRef, ...props }) => {
          return (
            <div
              data-slot="calendar"
              ref={rootRef}
              className={cn(className)}
              {...props}
            />
          )
        },
        Chevron: ({ className, orientation, ...props }) => {
          if (orientation === "left") {
            return (
              <ChevronLeftIcon className={cn("size-4", className)} {...props} />
            )
          }

          if (orientation === "right") {
            return (
              <ChevronRightIcon className={cn("size-4", className)} {...props} />
            )
          }

          return (
            <ChevronDownIcon className={cn("size-4", className)} {...props} />
          )
        },
        Day: ({ className, day, modifiers, ...props }) => {
          const isStart = Boolean(modifiers.range_start && !modifiers.range_end)
          const isEnd = Boolean(modifiers.range_end && !modifiers.range_start)
          const isMiddle = Boolean(modifiers.range_middle)

          return (
            <td
              className={cn(
                className,
                isStart &&
                  "relative isolate z-0 p-0 after:absolute after:inset-y-0 after:right-0 after:w-1/2 after:bg-forest/15 after:z-0 last:after:rounded-r-full",
                isMiddle &&
                  "relative isolate z-0 p-0 bg-forest/15 first:rounded-l-full last:rounded-r-full",
                isEnd &&
                  "relative isolate z-0 p-0 before:absolute before:inset-y-0 before:left-0 before:w-1/2 before:bg-forest/15 before:z-0 first:before:rounded-l-full"
              )}
              {...props}
            />
          )
        },
        DayButton: ({ ...props }) => (
          <CalendarDayButton locale={locale} {...props} />
        ),
        WeekNumber: ({ children, ...props }) => {
          return (
            <td {...props}>
              <div className="flex size-(--cell-size) items-center justify-center text-center">
                {children}
              </div>
            </td>
          )
        },
        ...components,
      }}
      {...props}
    />
  )
}

function CalendarDayButton({
  className,
  day,
  modifiers,
  locale,
  ...props
}: React.ComponentProps<typeof DayButton> & { locale?: Partial<Locale> }) {
  const defaultClassNames = getDefaultClassNames()

  const ref = React.useRef<HTMLButtonElement>(null)
  React.useEffect(() => {
    if (modifiers.focused) ref.current?.focus()
  }, [modifiers.focused])

  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      data-day={day.isoDate}
      data-selected-single={
        modifiers.selected &&
        !modifiers.range_start &&
        !modifiers.range_end &&
        !modifiers.range_middle
      }
      data-range-start={modifiers.range_start}
      data-range-end={modifiers.range_end}
      data-range-middle={modifiers.range_middle}
      className={cn(
        "relative isolate z-10 flex size-10 items-center justify-center p-0 rounded-full border-0 leading-none text-sm font-normal text-foreground cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-forest",
        "data-[range-start=true]:rounded-full data-[range-start=true]:bg-forest data-[range-start=true]:text-white data-[range-start=true]:font-medium data-[range-start=true]:hover:bg-forest-hover data-[range-start=true]:shadow-xs",
        "data-[range-end=true]:rounded-full data-[range-end=true]:bg-forest data-[range-end=true]:text-white data-[range-end=true]:font-medium data-[range-end=true]:hover:bg-forest-hover data-[range-end=true]:shadow-xs",
        "data-[range-middle=true]:rounded-full data-[range-middle=true]:bg-transparent data-[range-middle=true]:text-foreground data-[range-middle=true]:hover:bg-forest/20 data-[range-middle=true]:font-normal",
        "data-[selected-single=true]:rounded-full data-[selected-single=true]:bg-forest data-[selected-single=true]:text-white data-[selected-single=true]:font-medium data-[selected-single=true]:hover:bg-forest-hover data-[selected-single=true]:shadow-xs",
        "[&:not([data-range-start=true]):not([data-range-end=true]):not([data-range-middle=true]):not([data-selected-single=true])]:hover:bg-mist",
        className
      )}
      {...props}
    />
  )
}

export { Calendar, CalendarDayButton }
