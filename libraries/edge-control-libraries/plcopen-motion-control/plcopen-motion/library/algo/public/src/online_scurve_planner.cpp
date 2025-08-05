// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file online_scurve_planner.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/public/include/online_scurve_planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>
#include <algo/common/include/math_utils.hpp>

#define POLYNOMIAL_STOP

using namespace RTmotion;

namespace trajectory_processing
{
void ScurvePlannerOnLine::computeProfile(double jk, double t, double& ak,
                                         double& vk,
                                         double& sk)  // Equation (1)
{
  // Equation (1)
  ak = ak_ + (t - tk_) * (jk_ + jk) / 2.0;
  vk = vk_ + (t - tk_) * (ak_ + ak) / 2.0;
  sk = sk_ + (t - tk_) * (vk_ + vk) / 2.0;
}

void ScurvePlannerOnLine::computeStopPhaseDccProfile(double& /*jk*/, double& hk,
                                                     double& Tj2a, double& Tj2b,
                                                     double& Td)
{
  double amin = -condition_.a_max;
  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double ve   = condition_.v1;
  double ae   = condition_.a1;

  // Equation (4)
  Tj2a = (amin - ak_) / jmin;
  Tj2b = (ae - amin) / jmax;
  Td   = (ve - vk_) / amin + Tj2a * (amin - ak_) / (2 * amin) +
       Tj2b * (amin - ae) / (2 * amin);
  if (Td - (Tj2a + Tj2b) < 0)
  {
    // Equation (5)
    Tj2a =
        -ak_ / jmin + sqrt((jmax - jmin) *
                           (__square(ak_) * jmax -
                            jmin * (__square(ae) + 2.0 * jmax * (vk_ - ve)))) /
                          (jmin * (jmin - jmax));
    Tj2b =
        -ae / jmax + sqrt((jmax - jmin) *
                          (__square(ak_) * jmax -
                           jmin * (__square(ae) + 2.0 * jmax * (vk_ - ve)))) /
                         (jmin * (jmin - jmax));
    Td = Tj2a + Tj2b;
  }
  // Equation (6)
  hk = ak_ * __square(Td) / 2.0 +
       (jmin * Tj2a * (3.0 * __square(Td) - 3.0 * Td * Tj2a + __square(Tj2a)) +
        jmax * __cube(Tj2b)) /
           6.0 +
       Td * vk_;
}

void ScurvePlannerOnLine::computeStopPhaseAccProfile(double& /*jk*/, double& hk,
                                                     double& Tj2a, double& Tj2b,
                                                     double& Td)
{
  double amax = condition_.a_max;
  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double ve   = condition_.v1;
  double ae   = condition_.a1;

  // Equation (8)
  Tj2a = (amax - ak_) / jmax;
  Tj2b = (ae - amax) / jmin;
  Td   = (ve - vk_) / amax + Tj2a * (amax - ak_) / (2.0 * amax) +
       Tj2b * (amax - ae) / (2.0 * amax);
  if (Td - (Tj2a + Tj2b) < 0)
  {
    // Equation (9)
    Tj2a =
        -ak_ / jmax + sqrt((jmin - jmax) *
                           (__square(ak_) * jmin -
                            jmax * (__square(ae) + 2.0 * jmin * (vk_ - ve)))) /
                          (jmax * (jmax - jmin));
    Tj2b =
        -ae / jmin + sqrt((jmin - jmax) *
                          (__square(ak_) * jmin -
                           jmax * (__square(ae) + 2.0 * jmin * (vk_ - ve)))) /
                         (jmin * (jmin - jmax));
    Td = Tj2a + Tj2b;
  }

  // Equation (10)
  hk = ak_ * __square(Td) / 2.0 +
       (jmax * Tj2a * (3.0 * __square(Td) - 3.0 * Td * Tj2a + __square(Tj2a)) +
        jmin * __cube(Tj2b)) /
           6.0 +
       Td * vk_;
}

void ScurvePlannerOnLine::computeStopPhaseDcc(double t, double& jk, double& ak,
                                              double& vk, double& sk)
{
  double td   = profile_.Td;
  double tj2a = profile_.Tj2a;
  double tj2b = profile_.Tj2b;

  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double th   = profile_.Th;

#ifdef POLYNOMIAL_STOP
  static double h, a0, a1, a2, a3, a4, a5;
  if (phase_ != mcJerkMin)
  {
    phase_  = mcJerkMin;
    s_init_ = sk_;
    v_init_ = vk_;
    a_init_ = ak_;
    t_init_ = tk_;
    h       = fabs(condition_.q1 - s_init_);
    a0      = s_init_;
    a1      = v_init_;
    a2      = a_init_ / 2.0;
    a3      = (20 * h - (8 * condition_.v1 + 12 * v_init_) * td -
          (3 * a_init_ - condition_.a1) * __square(td)) /
         (2 * __cube(td));
    a4 = (-30 * h + (14 * condition_.v1 + 16 * v_init_) * td +
          (3 * a_init_ - 2 * condition_.a1) * __square(td)) /
         (2 * __square(td) * __square(td));
    a5 = (12 * h - 6 * (condition_.v1 + v_init_) * td +
          (condition_.a1 - a_init_) * __square(td)) /
         (2 * __square(td) * __cube(td));
    printf("Polynomial coeffs: a0 %f, a0 %f, a0 %f, a0 %f, a0 %f, a0 %f\n", a0,
           a1, a2, a3, a4, a5);
  }

  if (t - th < td)
  {
    double tt = t - t_init_;
    sk        = s_init_ + a1 * tt + a2 * __square(tt) + a3 * __cube(tt) +
         a4 * __square(tt) * __square(tt) + a5 * __square(tt) * __cube(tt);
    vk = v_init_ + 2 * a2 * tt + 3 * a3 * __square(tt) + 4 * a4 * __cube(tt) +
         5 * a5 * __square(tt) * __square(tt);
    ak = a_init_ + 6 * a3 * tt + 12 * a4 * __square(tt) + 20 * a5 * __cube(tt);
    jk = 6 * a3 + 24 * a4 * tt + 60 * a5 * __square(tt);
  }
#else
  // Equation (7)
  if (t - th < Tj2a)
  {
    if (phase_ != JerkMin)
    {
      phase_  = JerkMin;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    // double tt = t - th;
    double tt = t - t_init_;
    // (3.30e)
    jk = Jmin;
    ak = a_init_ - Jmax * tt;
    vk = v_init_ + a_init_ * tt - Jmax * __square(tt) / 2.0;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 -
         Jmax * __cube(tt) / 6.0;
  }
  if ((t - th) > Tj2a && (t - th) < (Td - Tj2b))
  {
    if (phase_ != JerkZero)
    {
      phase_  = JerkZero;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    // double tt = t - th - Tj2a;
    double tt = t - t_init_;
    // (3.30f)
    jk = 0;
    ak = a_init_;
    vk = v_init_ + a_init_ * tt;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0;
  }
  if ((t - th) > (Td - Tj2b) && (t - th) < Td)
  {
    if (phase_ != JerkMax)
    {
      phase_  = JerkMax;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    // double tt = t - th - (Td - Tj2b);
    double tt = t - t_init_;
    // (3.30g)
    jk = Jmax;
    ak = a_init_ + Jmax * tt;
    vk = v_init_ + a_init_ * tt + Jmax * __square(tt) / 2.0;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 +
         Jmax * __cube(tt) / 6.0;
  }
#endif
  if ((t - th) >= td)
  {
    jk = 0.0;
    ak = ak_;
    vk = vk_;
    sk = sk_;
  }
}

void ScurvePlannerOnLine::computeStopPhaseAcc(double t, double& jk, double& ak,
                                              double& vk, double& sk)
{
  double td   = profile_.Td;
  double tj2a = profile_.Tj2a;
  double tj2b = profile_.Tj2b;

  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double th   = profile_.Th;

#ifdef POLYNOMIAL_STOP
  static double h, a0, a1, a2, a3, a4, a5;
  if (phase_ != mcJerkMax)
  {
    phase_  = mcJerkMax;
    s_init_ = sk_;
    v_init_ = vk_;
    a_init_ = ak_;
    t_init_ = tk_;
    h       = fabs(condition_.q1 - s_init_);
    a0      = s_init_;
    a1      = v_init_;
    a2      = a_init_ / 2.0;
    a3      = (20 * h - (8 * condition_.v1 + 12 * v_init_) * td -
          (3 * a_init_ - condition_.a1) * __square(td)) /
         (2 * __cube(td));
    a4 = (-30 * h + (14 * condition_.v1 + 16 * v_init_) * td +
          (3 * a_init_ - 2 * condition_.a1) * __square(td)) /
         (2 * __square(td) * __square(td));
    a5 = (12 * h - 6 * (condition_.v1 + v_init_) * td +
          (condition_.a1 - a_init_) * __square(td)) /
         (2 * __square(td) * __cube(td));
    printf("Polynomial coeffs: a0 %f, a0 %f, a0 %f, a0 %f, a0 %f, a0 %f\n", a0,
           a1, a2, a3, a4, a5);
  }

  if (t - th < td)
  {
    double tt = t - t_init_;
    sk        = s_init_ + a1 * tt + a2 * __square(tt) + a3 * __cube(tt) +
         a4 * __square(tt) * __square(tt) + a5 * __square(tt) * __cube(tt);
    vk = v_init_ + 2 * a2 * tt + 3 * a3 * __square(tt) + 4 * a4 * __cube(tt) +
         5 * a5 * __square(tt) * __square(tt);
    ak = a_init_ + 6 * a3 * tt + 12 * a4 * __square(tt) + 20 * a5 * __cube(tt);
    jk = 6 * a3 + 24 * a4 * tt + 60 * a5 * __square(tt);
  }
#else
  // Equation (11)
  if (t - th < Tj2a)
  {
    if (phase_ != JerkMax)
    {
      phase_  = JerkMax;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30a)
    jk = Jmax;
    ak = a_init_ + Jmax * tt;
    vk = v_init_ + a_init_ * tt + Jmax * __square(tt) / 2.0;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 +
         Jmax * __cube(tt) / 6.0;
  }
  if ((t - th) > Tj2a && (t - th) < (Td - Tj2b))
  {
    if (phase_ != JerkZero)
    {
      phase_  = JerkZero;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30b)
    jk = 0;
    ak = a_init_;
    vk = v_init_ + a_init_ * tt;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0;
  }
  if ((t - th) > (Td - Tj2b) && sk_ < condition_.q1)
  {
    if (phase_ != JerkMin)
    {
      phase_  = JerkMin;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - th - (Td - Tj2b);
    // (3.30c)
    jk = Jmin;
    ak = a_init_ - Jmax * tt;
    vk = v_init_ + a_init_ * tt - Jmax * __square(tt) / 2;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 -
         Jmax * __cube(tt) / 6.0;
  }
#endif
  if ((t - th) >= td)
  {
    jk = 0.0;
    ak = ak_;
    vk = vk_;
    sk = sk_;
  }
}

void ScurvePlannerOnLine::computeFirstPhaseAcc(double t, double& jk, double& ak,
                                               double& vk,
                                               double& sk)  // v0 <= Vmax
{
  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double amax = condition_.a_max;
  double vmax = condition_.v_max;

  double tmp = vk_ - __square(ak_) / (2.0 * jmin);
  // Equation (2)
  if (tmp < vmax && ak_ < amax)  // Accelerate increase
  {
    if (phase_ != mcJerkMax)
    {
      phase_  = mcJerkMax;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30a)
    jk = jmax;
    ak = a_init_ + jmax * tt;
    vk = v_init_ + a_init_ * tt + jmax * __square(tt) / 2.0;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 +
         jmax * __cube(tt) / 6.0;
  }
  if (tmp < vmax && ak_ >= amax)  // Accelerate constant
  {
    if (phase_ != mcJerkZero)
    {
      phase_  = mcJerkZero;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30b)
    jk = 0.0;
    ak = amax;
    vk = v_init_ + amax * tt;
    sk = s_init_ + v_init_ * tt + amax * __square(tt) / 2.0;
  }
  if (tmp >= vmax && ak_ > 0.0)  // Accelerate decrease
  {
    if (phase_ != mcJerkMin)
    {
      phase_  = mcJerkMin;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30c)
    jk = jmin;
    ak = a_init_ - jmax * tt;
    vk = v_init_ + a_init_ * tt - jmax * __square(tt) / 2;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 -
         jmax * __cube(tt) / 6.0;
  }
  if (tmp >= vmax && ak_ <= 0.0)  // Constant velocity
  {
    if (phase_ != mcNoJerk)
    {
      phase_  = mcNoJerk;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30c)
    jk = 0.0;
    ak = 0.0;
    vk = v_init_;
    sk = s_init_ + v_init_ * tt;
  }
}

void ScurvePlannerOnLine::computeFirstPhaseDcc(double t, double& jk, double& ak,
                                               double& vk,
                                               double& sk)  // v0 > Vmax
{
  double jmin = -condition_.j_max;
  double jmax = condition_.j_max;
  double amin = -condition_.a_max;
  double vmax = condition_.v_max;
  // double ak = ak_;

  double tmp = vk_ - __square(ak_) / (2.0 * jmax);
  // Equation (3)
  // double jk = 0.0;
  if (tmp > vmax && ak_ > amin)  // Accelerate decrease
  {
    if (phase_ != mcJerkMin)
    {
      phase_  = mcJerkMin;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30c)
    jk = jmin;
    ak = a_init_ - jmax * tt;
    vk = v_init_ + a_init_ * tt - jmax * __square(tt) / 2;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 -
         jmax * __cube(tt) / 6.0;
  }
  if (tmp > vmax && ak_ <= amin)  // Accelerate constant
  {
    if (phase_ != mcJerkZero)
    {
      phase_  = mcJerkZero;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30b)
    jk = 0.0;
    ak = amin;
    vk = v_init_ + amin * tt;
    sk = s_init_ + v_init_ * tt + amin * __square(tt) / 2.0;
  }
  if (tmp <= vmax && ak_ < 0.0)  // Accelerate increase
  {
    if (phase_ != mcJerkMax)
    {
      phase_  = mcJerkMax;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    // (3.30a)
    jk = jmax;
    ak = a_init_ + jmax * tt;
    vk = v_init_ + a_init_ * tt + jmax * __square(tt) / 2.0;
    sk = s_init_ + v_init_ * tt + a_init_ * __square(tt) / 2.0 +
         jmax * __cube(tt) / 6.0;
  }
  if (tmp <= vmax && ak_ >= 0.0)  // Constant velocity
  {
    if (phase_ != mcNoJerk)
    {
      phase_  = mcNoJerk;
      s_init_ = sk_;
      v_init_ = vk_;
      a_init_ = ak_;
      t_init_ = tk_;
    }
    double tt = t - t_init_;
    jk        = 0.0;
    ak        = 0.0;
    vk        = v_init_;
    sk        = s_init_ + v_init_ * tt;
  }
}

double* ScurvePlannerOnLine::getWaypoint(double t)
{
  if (!triggered_)
  {
    triggered_ = true;
    sk_        = condition_.q0;
    vk_        = condition_.v0;
    ak_        = condition_.a0;
    jk_        = 0.0;
    tk_        = 0.0;
  }
  // printf("Debug t %f, q0 %f, v0 %f, q1 %f, v1 %f.\n", t, condition_.q0,
  // condition_.v0, condition_.q1, condition_.v1);

  double jk = 0.0;
  double ak, vk, sk;
  if (mode_ == mcNotYetStarted)
  {
    double jk_d, hk_d, tj2a_d, tj2b_d, td_d;
    double jk_a, hk_a, tj2a_a, tj2b_a, td_a;

    computeStopPhaseDccProfile(jk_d, hk_d, tj2a_d, tj2b_d, td_d);
    computeStopPhaseAccProfile(jk_a, hk_a, tj2a_a, tj2b_a, td_a);

    hk_d      = isnan(hk_d) ? 0.0 : hk_d;
    hk_a      = isnan(hk_a) ? 0.0 : hk_a;
    double hk = std::fmax(hk_d, hk_a);
    if (hk >= condition_.q1 - sk_)
    {
      // printf("Debug t %f, hk_d %f, hk_a %f, hk %f, s-sk %f.\n", t, hk_d,
      // hk_a,
      //  hk, condition_.q1 - sk_);
      if (hk == hk_d)
      {
        mode_         = mcDeceleration;
        profile_.Tj2a = tj2a_d;
        profile_.Tj2b = tj2b_d;
        profile_.Td   = td_d;
        profile_.Th   = tk_;
        // printf("Deceleration stop.\n");
      }
      else
      {
        mode_         = mcAcceleration;
        profile_.Tj2a = tj2a_a;
        profile_.Tj2b = tj2b_a;
        profile_.Td   = td_a;
        profile_.Th   = tk_;
        // printf("Acceleration stop.\n");
      }
    }
    else
    {
      if (condition_.v0 <= condition_.v_max)
      {
        computeFirstPhaseAcc(t, jk, ak, vk, sk);
        // printf("First Phase Aeceleration.\n");
      }
      else
      {
        computeFirstPhaseDcc(t, jk, ak, vk, sk);
        // printf("First Phase Deceleration.\n");
      }
    }
  }

  if (mode_ == mcDeceleration)
  {
    computeStopPhaseDcc(t, jk, ak, vk, sk);
  }
  else if (mode_ == mcAcceleration)
  {
    computeStopPhaseAcc(t, jk, ak, vk, sk);
  }
  // else
  // {
  //   computeProfile(jk, t, ak, vk, sk);
  // }

  point_[mcPositionId]     = sk;
  point_[mcSpeedId]        = vk;
  point_[mcAccelerationId] = ak;
  point_[mcJerkId]         = jk;

  sk_ = sk;
  vk_ = vk;
  ak_ = ak;
  jk_ = jk;
  tk_ = t;

  // printf("Debug t %f, sk %f, vk %f, ak %f, jk %f.\n", t, sk, vk, ak, jk);

  pointSignTransform(point_);

  return point_;
}

void ScurvePlannerOnLine::reset()
{
  sk_ = 0.0;
  vk_ = 0.0;
  ak_ = 0.0;
  jk_ = 0.0;
  tk_ = 0.0;

  profile_   = ScurveProfile();
  condition_ = ScurveCondition();
  triggered_ = false;
  mode_      = mcNotYetStarted;
}

}  // namespace trajectory_processing
