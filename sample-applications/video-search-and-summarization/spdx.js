const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Define the glob pattern to select files
const pattern = 'src/**/*.ts'; // change this to your desired pattern

// Define the header to add
const header = `
// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
`;

// Use glob to find files matching the pattern
glob(pattern, (err, files) => {
  if (err) {
    console.error('Error while globbing:', err);
    return;
  }

  files.forEach((file) => {
    // Read file content
    const content = fs.readFileSync(file, 'utf-8');

    // Check if header already exists to avoid duplicate headers
    if (content.startsWith(header)) {
      console.log(`Header already present in ${file}, skipping...`);
      return;
    }

    // Write back file with header prepended
    fs.writeFileSync(file, header + content, 'utf-8');
    console.log(`Header added to ${file}`);
  });
});
