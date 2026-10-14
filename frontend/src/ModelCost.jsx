import React from "react";

export function priceText(info) {
  const prices = Object.values(info.price_per_image || {});
  if (!prices.length) return "";
  let text = `from $${Math.min(...prices)} per image`;
  if (info.price_per_reference != null)
    text += ` + $${info.price_per_reference} per reference`;
  if (info.price_estimated) text += " (estimated)";
  return text;
}

export function ModelCost({ info }) {
  return <span>{[info.licence, priceText(info)].filter(Boolean).join(" · ")}</span>;
}
