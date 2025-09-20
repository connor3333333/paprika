# app.py
import streamlit as st
import json
import random
import re
import html
from collections import defaultdict
from fractions import Fraction
import streamlit.components.v1 as components

st.set_page_config(page_title="Weekly Meal Planner", layout="centered")

# -------------------------
# Utilities: amount parsing + consolidation
# -------------------------
UNICODE_FRAC_MAP = {
    "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"
}

UNIT_ALIASES = {
    "cups": "cup", "cup": "cup", "c": "cup",
    "tablespoons": "tbsp", "tablespoon": "tbsp", "tbsp": "tbsp", "tbsp.": "tbsp", "tbs": "tbsp",
    "teaspoons": "tsp", "teaspoon": "tsp", "tsp": "tsp", "tsp.": "tsp",
    "ounces": "oz", "ounce": "oz", "oz": "oz",
    "grams": "g", "gram": "g", "g": "g",
    "kilograms": "kg", "kg": "kg",
    "milliliters": "ml", "ml": "ml", "liters": "l", "l": "l",
    "large": "large", "small": "small", "can": "can", "cans": "can", "slice": "slice", "slices": "slice",
    "clove": "clove", "cloves": "clove", "pinch": "pinch", "package": "package", "packages": "package"
}

CONVERTIBLE_TO_TBSP = {"cup", "tbsp", "tsp"}  # we'll convert among these (base = tbsp)

def replace_unicode_fractions(s: str) -> str:
    for k, v in UNICODE_FRAC_MAP.items():
        s = s.replace(k, v)
    return s

def parse_amount(amount_str):
    if not amount_str:
        return None, None, ""
    s = str(amount_str).strip()
    s = replace_unicode_fractions(s)
    s = s.lower().strip()
    if not s or any(kw in s for kw in ("to taste", "as needed", "optional", "for serving")):
        return None, None, s

    m = re.match(r'^(\d+\s+\d+/\d+|\d+/\d+|\d+(\.\d+)?)(.*)$', s)
    if m:
        num_str = m.group(1).strip()
        rest = m.group(3).strip()
        try:
            qty = Fraction(num_str)
        except:
            try:
                qty = Fraction(float(num_str))
            except:
                qty = None

        unit_match = re.match(r'^(?:\([^)]*\)\s*)*([^\s,;()]+)', rest)
        unit_raw = unit_match.group(1) if unit_match else ""
        unit_raw = unit_raw.rstrip('.,')
        unit = UNIT_ALIASES.get(unit_raw, unit_raw) if unit_raw else None
        return qty, unit, rest
    else:
        wordnum = re.match(r'^(one|two|three|four|five|six|seven|eight|nine|ten)\b(.*)$', s)
        WORD_TO_INT = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10}
        if wordnum:
            qty = Fraction(WORD_TO_INT[wordnum.group(1)])
            rest = wordnum.group(2).strip()
            unit_match = re.match(r'^(?:\([^)]*\)\s*)*([^\s,;()]+)', rest)
            unit_raw = unit_match.group(1) if unit_match else ""
            unit_raw = unit_raw.rstrip('.,')
            unit = UNIT_ALIASES.get(unit_raw, unit_raw) if unit_raw else None
            return qty, unit, rest
        return None, None, s

def to_tbsp(qty: Fraction, unit: str):
    if qty is None or not unit:
        return None
    unit = unit.lower()
    if unit == "cup":
        return qty * 16
    if unit == "tbsp":
        return qty
    if unit == "tsp":
        return qty / 3
    return None

def frac_to_mixed_string(fr: Fraction):
    if fr == 0:
        return "0"
    sign = "-" if fr < 0 else ""
    fr = abs(fr)
    whole = fr.numerator // fr.denominator
    remainder = fr - whole
    if whole and remainder:
        return f"{sign}{whole} {remainder}"
    elif whole:
        return f"{sign}{whole}"
    else:
        return f"{sign}{remainder}"

def format_tbsp_total(total_tbsp: Fraction):
    if total_tbsp >= 16:
        total_cups = total_tbsp / 16
        return f"{frac_to_mixed_string(total_cups)} cup"
    elif total_tbsp >= 1:
        return f"{frac_to_mixed_string(total_tbsp)} tbsp"
    else:
        total_tsp = total_tbsp * 3
        return f"{frac_to_mixed_string(total_tsp)} tsp"

def consolidate_entries(entries):
    convertible_totals = []
    same_unit_group = defaultdict(Fraction)
    raw_ones = []

    for e in entries:
        qty = e.get("qty")
        unit = e.get("unit")
        raw = e.get("raw") or ""
        if qty is not None and unit in CONVERTIBLE_TO_TBSP:
            tb = to_tbsp(qty, unit)
            if tb is not None:
                convertible_totals.append(tb)
            else:
                raw_ones.append(raw or "")
        elif qty is not None and unit:
            same_unit_group[unit] += qty
        else:
            if raw:
                raw_ones.append(raw)
            else:
                raw_ones.append("")

    parts = []
    if convertible_totals:
        total_tbsp = sum(convertible_totals, Fraction(0))
        parts.append(format_tbsp_total(total_tbsp))

    for unit, total in same_unit_group.items():
        parts.append(f"{frac_to_mixed_string(total)} {unit}")

    if raw_ones:
        uniq = []
        for r in raw_ones:
            if r and r not in uniq:
                uniq.append(r)
        if uniq:
            parts.append(" + ".join(uniq))

    if parts:
        return " + ".join(parts)
    return ""

# -------------------------
# Load recipes
# -------------------------
@st.cache_data
def load_recipes(path="recipes.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

recipes = load_recipes()
DAYS = ["sunday", "sunday meal prep", "monday", "tuesday", "wednesday", "thursday"]
categories_map = defaultdict(list)
for r in recipes:
    cat = (r.get("category") or "").strip().lower()
    categories_map[cat].append(r)

# -------------------------
# HTML building
# -------------------------
def build_html(meal_plan, shopping_by_dept):
    safe = lambda s: html.escape(str(s))
    html_parts = []
    html_parts.append("<!doctype html><html><head><meta charset='utf-8'><title>Weekly Meal Plan</title>")
    html_parts.append("""
    <style>
      body{font-family: Arial, Helvetica, sans-serif; padding:20px; color:#222; text-align:center;}
      h1{color:#2b6cb0;}
      h2{color:#234e52;}
      .day{margin-bottom:12px;}
      .recipe-title{font-weight:700;}
      .section{margin-top:18px; margin-bottom:18px;}
      .ingredients, .directions {margin-left:18px; text-align:left;}
      .shopping-list{column-count:1; margin-left:18px; text-align:left;}
      @media(min-width:800px){ .shopping-list{column-count:2;} }
      .meta { font-style: italic; color:#555; margin-bottom:6px; text-align:center; }
      .source { font-size: small; color:#555; }
    </style>
    """)
    html_parts.append("</head><body>")
    html_parts.append("<h1>Weekly Meal Plan</h1>")

    html_parts.append("<div class='section'><h2>Shopping List</h2><div class='shopping-list'>")
    for dept, items in shopping_by_dept.items():
        html_parts.append(f"<h3>{safe(dept)}</h3><ul>")
        for name, display_amount in items.items():
            if display_amount:
                html_parts.append(f"<li>{safe(name)}: {safe(display_amount)}</li>")
            else:
                html_parts.append(f"<li>{safe(name)}</li>")
        html_parts.append("</ul>")
    html_parts.append("</div></div>")

    html_parts.append("<div class='section'><h2>Selected Meals</h2>")
    for day in DAYS:
        r = meal_plan.get(day)
        if not r:
            continue
        html_parts.append(f"<div class='day'><div class='recipe-title'>{safe(day.title())}: {safe(r.get('title',''))}</div>")
        meta_items = []
        if r.get("prep_time"):
            meta_items.append(f"Prep: {safe(r.get('prep_time'))}")
        if r.get("cook_time"):
            meta_items.append(f"Cook: {safe(r.get('cook_time'))}")
        if r.get("servings"):
            meta_items.append(f"Servings: {safe(r.get('servings'))}")
        if meta_items:
            html_parts.append("<div class='meta'>" + " | ".join(meta_items) + "</div>")

        if r.get("ingredients"):
            html_parts.append("<div class='ingredients'><strong>Ingredients:</strong><ul>")
            for ing in r.get("ingredients"):
                name = ing.get("name","")
                amount = ing.get("amount","")
                dept = ing.get("department","")
                html_parts.append(f"<li>{safe(name)}: {safe(amount)} <em>({safe(dept)})</em></li>")
            html_parts.append("</ul></div>")

        if r.get("directions"):
            html_parts.append("<div class='directions'><strong>Directions:</strong><ol>")
            for step in r.get("directions"):
                html_parts.append(f"<li>{safe(step)}</li>")
            html_parts.append("</ol></div>")

        if r.get("notes"):
            html_parts.append("<div class='notes'><strong>Notes:</strong><ul>")
            for note in r.get("notes"):
                html_parts.append(f"<li>{safe(note)}</li>")
            html_parts.append("</ul></div>")

        if r.get("nutrition"):
            html_parts.append("<div class='nutrition'><strong>Nutrition:</strong><ul>")
            for k, v in r.get("nutrition").items():
                html_parts.append(f"<li>{safe(k)}: {safe(v)}</li>")
            html_parts.append("</ul></div>")

        if r.get("source"):
            html_parts.append(f"<div class='source'>Source: <a href='{safe(r['source'])}' target='_blank'>{safe(r['source'])}</a></div>")

        html_parts.append("</div>")

    html_parts.append("</div></body></html>")
    return "\n".join(html_parts)

# -------------------------
# Streamlit UI
# -------------------------
col = st.columns(1)[0]  # single full-width column for centering
with col:
    st.title("Weekly Meal Planner 🍽️")

    if "options" not in st.session_state:
        st.session_state.options = {}
    if "temp_selection" not in st.session_state:
        st.session_state.temp_selection = {}
    if "finalized" not in st.session_state:
        st.session_state.finalized = False
    if "meal_plan" not in st.session_state:
        st.session_state.meal_plan = {}

    if st.button("Generate Meal Plan"):
        st.session_state.options = {}
        st.session_state.temp_selection = {}
        st.session_state.finalized = False
        st.session_state.meal_plan = {}

        for day in DAYS:
            pool = categories_map.get(day, [])
            if len(pool) >= 2:
                st.session_state.options[day] = random.sample(pool, 2)
            else:
                st.session_state.options[day] = pool[:]
        st.success("Generated choices for each day. Pick one for each day below.")

    if st.button("Reset"):
        st.session_state.options = {}
        st.session_state.temp_selection = {}
        st.session_state.finalized = False
        st.session_state.meal_plan = {}
        st.rerun()

    st.write("## Choose meals (pick one per category)")
    if not st.session_state.options:
        st.info("Click **Generate Meal Plan** to get two random options per category.")
    else:
        for day in DAYS:
            options = st.session_state.options.get(day, [])
            if not options:
                st.info(f"No recipes found for **{day.title()}**.")
                continue
            titles = [o.get("title","Untitled") for o in options]
            idx = 0
            prev = st.session_state.temp_selection.get(day)
            if prev in titles:
                idx = titles.index(prev)
            if len(titles) == 1:
                st.markdown(f"<div style='text-align:center'><strong>{day.title()}:</strong> {titles[0]}</div>", unsafe_allow_html=True)
                st.session_state.temp_selection[day] = titles[0]
            else:
                choice = st.radio(f"{day.title()}:", titles, index=idx, key=f"radio_{day}")
                st.session_state.temp_selection[day] = choice

        if st.button("Finalize Plan"):
            plan = {}
            for day in DAYS:
                chosen_title = st.session_state.temp_selection.get(day)
                if not chosen_title:
                    continue
                opt_list = st.session_state.options.get(day, [])
                chosen = next((r for r in opt_list if r.get("title") == chosen_title), None)
                if chosen:
                    plan[day] = chosen
            st.session_state.meal_plan = plan
            st.session_state.finalized = True
            st.success("Meal plan finalized — scroll down for shopping list, preview, and export.")

    if st.session_state.finalized and st.session_state.meal_plan:
        st.markdown("---")
        st.header("Finalized Weekly Meal Plan")
        cols_preview = st.columns(3)
        for i, day in enumerate(DAYS):
            r = st.session_state.meal_plan.get(day)
            with cols_preview[i % 3]:
                if r:
                    st.markdown(f"<div style='text-align:center'><strong>{day.title()}</strong><br>{r.get('title')}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='text-align:center'><strong>{day.title()}</strong><br>_No selection_</div>", unsafe_allow_html=True)

        # Build shopping list
        shopping_temp = defaultdict(lambda: defaultdict(list))
        for recipe in st.session_state.meal_plan.values():
            for ing in recipe.get("ingredients", []):
                name = ing.get("name", "").strip()
                amount_raw = ing.get("amount", "") or ""
                dept = ing.get("department", "Other") or "Other"
                qty, unit, rest = parse_amount(amount_raw)
                shopping_temp[dept][name].append({
                    "raw": amount_raw,
                    "qty": qty,
                    "unit": unit,
                    "rest": rest
                })

        shopping_final = {}
        for dept, items in shopping_temp.items():
            shopping_final[dept] = {}
            for name, entries in items.items():
                display_amount = consolidate_entries(entries)
                shopping_final[dept][name] = display_amount

        # HTML preview + download
        html_str = build_html(st.session_state.meal_plan, shopping_final)

        st.header("HTML Preview")
        components.html(html_str, height=600, scrolling=True)

        st.download_button(
            label="📥 Download Meal Plan (.html)",
            data=html_str,
            file_name="meal_plan.html",
            mime="text/html"
        )

        st.caption("Tip: open the downloaded HTML and use your browser's Print → Save as PDF to create a PDF.")
