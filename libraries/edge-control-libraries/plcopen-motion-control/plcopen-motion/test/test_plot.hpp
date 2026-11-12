// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2026 Intel Corporation
#pragma once

#ifdef PLOT
#include <algorithm>
#include <cctype>
#include <map>
#include <string>
#include <vector>
#include "gtest/gtest.h"
#include <plot/matplotlibcpp.h>

// Plot ownership is local to the test; no pointers to test subjects are
// retained.
namespace test_plot
{
namespace plt = matplotlibcpp;

class TestPlot
{
public:
  explicit TestPlot(const std::string& prefix        = "function_block_test",
                    size_t panel_height              = 280,
                    const std::string& stacked_panel = "")
    : prefix_(prefix)
    , panel_height_(panel_height)
    , stacked_panel_(stacked_panel)
  {
  }
  void add(const std::string& panel, const std::string& label, double x,
           double value)
  {
    auto& trace = panels_[panel][label];
    trace.x.push_back(x);
    trace.y.push_back(value);
  }

  bool empty() const
  {
    return panels_.empty();
  }

  static std::string filename(const std::string& suffix = "",
                              const std::string& prefix = "function_block_test")
  {
    const auto* test = ::testing::UnitTest::GetInstance()->current_test_info();
    const std::string name = prefix + "." + test->test_suite_name() + "." +
                             test->name() +
                             (suffix.empty() ? "" : "." + suffix);
    // Escape rather than replace, so parameter separators cannot collide with
    // literal underscores in ordinary test names.
    std::string result;
    constexpr char hex[] = "0123456789ABCDEF";
    for (unsigned char c : name)
    {
      if (std::isalnum(c) || c == '.' || c == '-' || c == '_')
        result += static_cast<char>(c);
      else
      {
        result += '%';
        result += hex[c >> 4];
        result += hex[c & 15];
      }
    }
    return result + ".png";
  }

  static void recordFile(const std::string& file)
  {
    const auto* test = ::testing::UnitTest::GetInstance()->current_test_info();
    std::string files;
    if (test)
      for (int i = 0; i < test->result()->test_property_count(); ++i)
      {
        const auto& property = test->result()->GetTestProperty(i);
        if (std::string(property.key()) == "plot_files")
          files = property.value();
      }
    size_t start = 0;
    while (start < files.size())
    {
      const auto end = files.find(';', start);
      if (files.substr(start, end - start) == file)
        return;
      if (end == std::string::npos)
        break;
      start = end + 1;
    }
    if (!files.empty())
      files += ";";
    ::testing::Test::RecordProperty("plot_files", files + file);
    ::testing::Test::RecordProperty("plot", files + file);
  }

  void save(const std::string& suffix = "", const std::string& description = "",
            const std::string& xlabel = "Time (s)") const
  {
    if (empty())
      return;
    const auto* test = ::testing::UnitTest::GetInstance()->current_test_info();
    size_t height    = panel_height_ * panels_.size();
    const auto signals = panels_.find(stacked_panel_);
    if (signals != panels_.end())
      height +=
          std::max(panel_height_, 30 * signals->second.size()) - panel_height_;
    plt::figure_size(1600, height);
    size_t index = 0;
    for (const auto& panel : panels_)
    {
      plt::subplot(panels_.size(), 1, ++index);
      if (index == 1)
        plt::title(std::string(test->test_suite_name()) + "." + test->name() +
                   (description.empty() ? "" : "\n" + description));
      std::vector<double> ticks;
      std::vector<std::string> labels;
      for (const auto& item : panel.second)
      {
        auto values = item.second.y;
        if (panel.first == stacked_panel_)
        {
          const double offset = 2 * ticks.size();
          for (auto& value : values)
            value += offset;
          ticks.push_back(offset + 0.5);
          labels.push_back(item.first);
        }
        plt::named_plot(item.first, item.second.x, values,
                        values.size() == 1 ? "o" : "-");
      }
      if (panel.first == stacked_panel_)
        plt::yticks(ticks, labels);
      else
        plt::legend();
      plt::ylabel(panel.first == stacked_panel_ ? "0/1, offset per signal" :
                                                  panel.first);
      plt::xlabel(xlabel);
      plt::grid(true);
    }
    plt::tight_layout();
    const auto file = filename(suffix, prefix_);
    plt::save(file);
    plt::close();
    recordFile(file);
  }

private:
  struct Trace
  {
    std::vector<double> x, y;
  };
  std::map<std::string, std::map<std::string, Trace>> panels_;
  std::string prefix_;
  size_t panel_height_;
  std::string stacked_panel_;
};
}  // namespace test_plot
#endif
