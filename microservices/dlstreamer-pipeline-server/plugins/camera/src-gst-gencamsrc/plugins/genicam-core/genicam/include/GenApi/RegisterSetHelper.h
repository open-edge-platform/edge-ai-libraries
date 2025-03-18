//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Alexander Happe / Fritz Dierks
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
    \brief    Definition of CRegisterSetHelper
    \ingroup GenApi_PublicUtilities
*/


#ifndef REGISTER_SET_HELPER_H
#define REGISTER_SET_HELPER_H

namespace GENAPI_NAMESPACE
{
    /**
    \brief Copies data from buffer to variables in a typesafe manner
    \ingroup GenApi_PublicUtilities
    */
    class GENAPI_DECL CRegisterSetHelper
    {
    public:
        //! memcpy firing exceptions
        static size_t CopyData( void *pvDestination, size_t nbyDestSize, const void *pvSource, size_t nbySourceSize )
        {
            if (nbyDestSize != nbySourceSize)
            {
                throw OUT_OF_RANGE_EXCEPTION("CopyData : Destination size (%ld) does not fit source size (%d)", nbyDestSize, nbySourceSize);
            }

#if defined(_WINDOWS_)
            if ( IsBadWritePtr(pvDestination, nbyDestSize) || IsBadReadPtr(pvSource, nbySourceSize) )
            {
                throw RUNTIME_EXCEPTION("Invalid user buffer");
            }
#endif

            memcpy( pvDestination, pvSource, nbySourceSize );
            return nbySourceSize;
        }

        /**
        \brief Typesafe copy from variable to buffer
        */
        template<typename T>
        static size_t CopyToBuffer( void *pvDestination, size_t nbyDestSize, T *d )
        {
            return CopyData( pvDestination, nbyDestSize, d, sizeof( *d ) );
        }

        /**
        \brief Typesafe copy from buffer to variable
        */
        template<typename T>
        static size_t CopyFromBuffer( T *d, const void *pvDestination, size_t nbyDestSize)
        {
            return CopyData( d, sizeof( *d ), pvDestination, nbyDestSize);
        }
    };

} // namespace GenApi

#endif // ifndef REGISTER_SET_HELPER_H
