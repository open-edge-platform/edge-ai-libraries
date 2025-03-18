//-----------------------------------------------------------------------------
//  (c) 2007 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Contains GenApi's linker directives
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_GENAPILINKAGE_H
#define GENAPI_GENAPILINKAGE_H

#include <Base/GCLinkage.h>

// you can define GENICAM_NO_AUTO_IMPLIB to turn off automatic linkage of genicam libs
// you can define GENICAM_FORCE_AUTO_IMPLIB to enforce automatic linkage of genicam libs
#if defined(GENICAM_FORCE_AUTO_IMPLIB) || (!defined(GENICAM_NO_AUTO_IMPLIB) && !defined(GCBASE_EXPORTS) && !defined(GENAPI_EXPORTS)  && !defined(MATHPARSERDLL_EXPORTS) && !defined(LOG_EXPORTS))
#   if defined (_WIN32) && defined (_MT )
#       pragma comment(lib, LIB_NAME( "GCBase" ))
#       pragma comment(lib, LIB_NAME( "GenApi" ))
//#       pragma comment(lib, LIB_NAME( "Log" ))
//#       pragma comment(lib, LIB_NAME( "Log4cpp" ))
#   else
#       error Invalid configuration
#   endif
#endif


#define GENAPI_GENAPILINKAGE_H
#endif //
