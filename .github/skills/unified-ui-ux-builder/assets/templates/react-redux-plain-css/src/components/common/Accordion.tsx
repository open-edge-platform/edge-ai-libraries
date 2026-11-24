// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Collapsible panel pattern used throughout stack B for config/results
// sections. Mirrors the reference app's src/components/common/Accordion.tsx.
// See references/component-library.md "Stack B > Cards / panels".

import React, { useState } from 'react';
import './Accordion.css';

interface AccordionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

const Accordion: React.FC<AccordionProps> = ({ title, children, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="accordion">
      <div className="accordion-header" onClick={() => setIsOpen((open) => !open)}>
        <h3>{title}</h3>
        <button className="accordion-toggle" type="button" aria-label={isOpen ? 'Collapse' : 'Expand'}>
          {isOpen ? <span>&#x25BC;</span> : <span>&#x25B6;</span>}
        </button>
      </div>
      {isOpen && <div className="accordion-content">{children}</div>}
    </div>
  );
};

export default Accordion;
