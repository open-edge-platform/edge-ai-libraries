//-----------------------------------------------------------------------------
//  (c) 2009 by Basler Vision Technologies
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
\brief    Definition of interface IPort
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_PORTWRITELIST_H
#define GENAPI_PORTWRITELIST_H

#include <GenApi/IPortRecorder.h>
#include <list>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //! Container holding a list of port write commands
    class GENAPI_DECL CPortWriteList : public IPortWriteList
    {
    public:
        //! Constructor
        CPortWriteList();

        //! Destructor
        ~CPortWriteList();

        /*---------------------------------------------------------------*/
        // IPortWriteList
        /*---------------------------------------------------------------*/

        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length);

        //! Replays the write command to the given port interface
        virtual void Replay(IPort* pPort);

        //! Sets a cookie in case the port implementation want to cache a command list
        // Default = -1
        virtual void SetCookie(const int64_t Value);

        //! Gets the cookie a port implementation may have set for caching a command list
        virtual int64_t GetCookie();

    protected:
        //! The data associated with a write command
        typedef struct
        {
            int64_t Address;
            int64_t Length;
            char *pData;
        } WriteCommand_t;

        //! a list holding the write commands
        std::list<WriteCommand_t> *m_pWriteCommands;

        //! A cookie helper for caching
        int64_t m_Cookie;
    };

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_PORTWRITELIST_H
