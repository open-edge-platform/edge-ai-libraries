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

#ifndef GENAPI_IPORTRECORDER_H
#define GENAPI_IPORTRECORDER_H

#include <GenApi/IPort.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    interface GENAPI_DECL_ABSTRACT IPortWriteList
    {
        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length) = 0;

        //! Replays the write command to the given port interface
        virtual void Replay(IPort* pPort) = 0;

        //! Sets a cookie in case the port implementation want to cache a command list
        // Default = -1
        virtual void SetCookie(const int64_t Value) = 0;

        //! Gets the cookie a port implementation may have set for caching a command list
        virtual int64_t GetCookie() = 0;
    };

    /**
    \brief Interface for replaying write commands on a port
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IPortReplay : virtual public IPort
    {
        //! sends the commands to the camera.
        /*! the default implementation just walks the list and issues each command
            using the WriteRegister method. Depending on the capabilities of
            the transport layer the implementation can however use a special command
            which sends all register write commands as one package.
        */
        virtual void Replay( IPortWriteList *pPortRecorder, bool Invalidate = true ) = 0;
    };

    /**
    \brief Interface for recording write commands on a port
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IPortRecorder : public IPortReplay
    {
        //! starts logging all WriteRegister commands to a list
        virtual void StartRecording( IPortWriteList *pPortRecorder ) = 0;

        //! stops recording
        virtual void StopRecording() = 0;
    };

    //*************************************************************
    // CPortRecorderRef class
    //*************************************************************

    /**
    \internal
    \brief Reference to an IPortRecorder pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T>
    class CPortRecorderRefT : public CPortRefT<T>
    {
        typedef CPortRefT<T> ref;

    public:
        /*--------------------------------------------------------*/
        // IPortRecorder
        /*--------------------------------------------------------*/

        //! sends the commands to the camera.
        /*! the default implementation just walks the list and issues each command
        using the WriteRegister method. Depending on the capabilities of
        the transport layer the implementation can however use a special command
        which sends all register write commands as one package.
        */
        virtual void Replay( IPortWriteList *pPortRecorder, bool Invalidate = true )
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->Replay(pPortRecorder, Invalidate);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! starts logging all WriteRegister commands to a list
        virtual void StartRecording( IPortWriteList *pPortRecorder )
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->StartRecording(pPortRecorder);
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

        //! stops recording
        virtual void StopRecording()
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->StopRecording();
            else
                throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        }

    };

    //! Reference to an IPortRecorder pointer
    //! \ingroup GenApi_PublicImpl
    typedef CPortRecorderRefT< IPortRecorder > CPortRecorderRef;

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IPORTRECORDER_H
