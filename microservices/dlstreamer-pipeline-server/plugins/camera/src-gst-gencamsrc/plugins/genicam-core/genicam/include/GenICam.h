/****************************************************************************
 (c) 2005 by STEMMER IMAGING

 License: This file is published under the license of the EMVA GenICam  Standard Group.
 A text file describing the legal terms is included in  your installation as 'license.txt'.
 If for some reason you are missing  this file please contact the EMVA or visit the website
 (http://www.genicam.org) for a full copy.

 THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
 AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
 OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
 EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
 PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
 OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
 WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
 ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 POSSIBILITY OF SUCH DAMAGE.

****************************************************************************/

 /// \file     $Source$
 /// \brief    Common GenICam include file.
 /// \version  $Revision$
 /// \date     $Date$


#ifndef GENICAM_OVERALL_H
#define GENICAM_OVERALL_H

#if defined (_WIN32) || (defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__)) || defined(VXWORKS))
#   include <Base/GCBase.h>
#   include <GenApi/GenApi.h>
#else
#   error Unknown/unsupported platform
#endif

#endif // GENICAM_OVERALL_H
