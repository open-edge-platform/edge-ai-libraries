//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
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
\brief    Definition of interface IPortConstruct
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_IPORTCONSTRUCT_H
#define GENAPI_IPORTCONSTRUCT_H

#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/IPort.h>

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // IPortContruct interface
    //*************************************************************

    /**
    \brief Interface for ports
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT IPortConstruct: virtual public IPort
    {
        //! Sets pointer the real port implementation; this function may called only once
        virtual void SetPortImpl(IPort* pPort) = 0;

        //! Determines if the port adapter must perform an endianess swap
        virtual EYesNo GetSwapEndianess() = 0;
    };
}

#endif // ifndef GENAPI_IPORTCONSTRUCT_H
