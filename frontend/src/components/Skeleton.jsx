import React from 'react';

export default function Skeleton({ lines = 5 }) {
  return (
    <div className="skeleton-block">
      <div className="skeleton skeleton-heading"></div>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className={
            'skeleton skeleton-line ' +
            (i % 3 === 0 ? 'short' : i % 3 === 1 ? 'medium' : '')
          }
        ></div>
      ))}
    </div>
  );
}
