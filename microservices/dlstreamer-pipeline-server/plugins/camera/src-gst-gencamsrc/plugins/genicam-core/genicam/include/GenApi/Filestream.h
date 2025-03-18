//-----------------------------------------------------------------------------
//  (c) 2007 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Thies Moeller
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
\brief    Definition of ODevFileStream and IDevFileStream
*/

#ifndef GENAPI_FILESTREAM_H_
#define GENAPI_FILESTREAM_H_

// #include <algorithm>
// #include <iostream>
// #include <streambuf>
#include <iomanip>
#include <iosfwd>
#include <cstring> // memcpy
//#include <cstdlib>
//#include <memory>

#include <Base/GCUtilities.h>

#include <GenICamFwd.h>


#if (__GNUC__)
#  include <unistd.h>
#endif

// We cannot use std::streamsize because in VC90/Win32 this was int but in VC120 it is int64
// So in order to preserve compiler interoperability we need to use our own declaration
typedef int64_t GenICam_streamsize;


// FileProtocolAdapter was a header only class before.
// Since it has been moved to GenApi.dll the user now has to explicitly link against GenApi import library to use it
// To minimize the pain we add the genapi lib  using pragmas
#if defined (_MSC_VER)

#   include <Base/GCLinkage.h>

// you can define GENICAM_NO_AUTO_IMPLIB to turn off automatic linkage of genicam libs
// you can define GENICAM_FORCE_AUTO_IMPLIB to enforce automatic linkage of genicam libs
#   if defined(GENICAM_FORCE_AUTO_IMPLIB) || (!defined(GENICAM_NO_AUTO_IMPLIB) && !defined(GENAPI_EXPORTS))
#       if defined (_WIN32) && defined (_MT )
#           pragma comment(lib, LIB_NAME( "GenApi" ))
#       else
#           error Invalid configuration
#       endif
#   endif

#endif // _MSC_VER

#if defined (_MSC_VER)
#   pragma warning(push)
#   pragma warning (disable: 4251) //  class 'GenApi::CPointer<T>' needs to have dll-interface to be used by clients of class 'GenICam::FileProtocolAdapter'
#endif

namespace GENAPI_NAMESPACE
{
    /**
    \brief Adapter between the std::iostreambuf and the SFNC Features representing the device filesystem
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT IFileProtocolAdapter
    {
        virtual bool attach(GENAPI_NAMESPACE::INodeMap * pInterface) = 0;
        virtual bool openFile(const char * pFileName, std::ios_base::openmode mode) = 0;
        virtual bool closeFile(const char * pFileName) = 0;
        virtual GenICam_streamsize write(const char * buf, int64_t offs, int64_t len, const char * pFileName) = 0;
        virtual GenICam_streamsize read(char * buf, int64_t offs, GenICam_streamsize len, const char * pFileName) = 0;
        virtual int64_t getBufSize(const char * pFileName, std::ios_base::openmode mode) = 0;
        virtual bool deleteFile(const char * pFileName) = 0;

    };
    /*!
    * @brief
    * Adapter between the std::iostreambuf and the SFNC Features representing the device filesystem
    *
    * The adapter assumes, that the features provide stdio fileaccess
    * compatible semantic
    *
    */
    class GENAPI_DECL FileProtocolAdapter : public IFileProtocolAdapter {
    public:
        /*!
        * @brief
        * Constructor
        *
        */
        FileProtocolAdapter();
        virtual ~FileProtocolAdapter();
    private:
        FileProtocolAdapter(const FileProtocolAdapter&); // not implemented
        FileProtocolAdapter& operator=(const FileProtocolAdapter&); // not implemented
    public:
        
        /*!
        * @brief
        * attach file protocol adapter to nodemap
        *
        * @param pInterface
        * NodeMap of the device to which the FileProtocolAdapter is attached
        *
        * @return true if attach was successful, false if not
        *
        */
        virtual bool attach(GENAPI_NAMESPACE::INodeMap * pInterface );


        /*!
        * @brief
        * open a file on the device
        *
        * @param pFileName
        * file name of the file to open. The file name must exist in the Enumeration FileSelector
        *
        * @param mode
        * mode to open the file. The mode must exist in the Enumeration FileOpenMode
        *
        * @returns
        * true on success, false on error
        *
        */
        virtual bool openFile(const char * pFileName, std::ios_base::openmode mode);


        /*!
        * @brief
        * close a file on the device
        *
        * @param pFileName
        * file name of the file to open. The file name must exist in the Enumeration FileSelector
        *
        * @returns
        * true on success, false on error
        */
        virtual bool closeFile(const char * pFileName);


        /*!
        * @brief
        * writes data into a file.
        *
        * @param buf
        * source buffer
        *
        * @param offs
        * offset into the device file
        *
        * @param len
        * count of bytes to write
        *
        * @param pFileName
        * file name of the file to write into The file name must exist in the Enumeration FileSelector
        *
        * @returns
        * count of bytes written
        *
        */
        virtual GenICam_streamsize write(const char * buf, int64_t offs, int64_t len, const char * pFileName);


        /*!
        * @brief
        * read data from the device into a buffer
        *
        * @param buf
        * target buffer
        *
        * @param offs
        * offset in the device file to read from
        *
        * @param len
        * count of bytes to read
        *
        * @param pFileName
        * file name of the file to write into The file name must exist in the Enumeration FileSelector
        *
        * @returns
        * count of bytes successfully read
        *
        */
        virtual GenICam_streamsize read(char * buf, int64_t offs, GenICam_streamsize len, const char * pFileName);


        /*!
        * @brief
        * fetch max FileAccessBuffer length for a file
        *
        * @param pFileName
        * file name of the file to open. The file name must exist in the Enumeration FileSelector
        *
        * @param mode
        * mode to open the file. The mode must exist in the Enumeration FileOpenMode
        *
        * @returns
        * max length of FileAccessBuffer in the given mode on the given file
        *
        */
        virtual int64_t getBufSize(const char * pFileName, std::ios_base::openmode mode);


        /*!
        * @brief
        * Delete the content of the file.
        *
        * @param pFileName
        * file name of the file to open. The file name must exist in the Enumeration FileSelector
        *
        * @returns
        * true on success, false on error
        */
        virtual bool deleteFile(const char * pFileName);

    private:
        void WaitUntilFileOperationExecuteDone( bool Validate = true );

    private:
        // implementation details
        struct FileProtocolAdapterImpl;
        FileProtocolAdapterImpl* m_pImpl;
    };


    template<typename CharType, typename Traits> class IDevFileStreamBuf
        : public std::basic_streambuf<CharType, Traits> {

            typedef Traits traits_type;
            typedef typename Traits::int_type int_type;
            typedef typename Traits::char_type char_type;
            typedef IDevFileStreamBuf<CharType, Traits> filebuf_type;

            // GET next ptr
            using std::basic_streambuf<CharType, Traits>::gptr;
            // GET end ptr
            using std::basic_streambuf<CharType, Traits>::egptr;
            // GET begin ptr
            using std::basic_streambuf<CharType, Traits>::eback;
            // increment next pointer
            using std::basic_streambuf<CharType, Traits>::gbump;
            // set buffer info
            using std::basic_streambuf<CharType, Traits>::setg;

    public:
        IDevFileStreamBuf()
            : m_pBuffer(0), m_BufSize(0), m_pAdapter(0), m_fpos(0) {
                // This already handled by the base class constructor, right?
        // std::basic_streambuf<CharType, Traits>::_Init();
        };


        ~IDevFileStreamBuf()
        {
            // catch and dump all exceptions - we're in a destructor...
            try
            {
                this->close();
            }
            catch(...)
            {}
        }

        filebuf_type *open(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName, std::ios_base::openmode mode = std::ios_base::in ) {
            // get file protocol adapter
            m_pAdapter = new FileProtocolAdapter();

            // open file via Adapter
            if (!m_pAdapter || !m_pAdapter->attach(pInterface)){
                delete m_pAdapter;
                m_pAdapter = 0;
                return 0;
            }

            // open file via Adapter
            try
            {
                if (!(m_pAdapter->openFile(pFileName, mode))){
                    delete m_pAdapter;
                    m_pAdapter = 0;
                    return 0;
                }
            }
            catch (...)
            {
                delete m_pAdapter;
                m_pAdapter = 0;
                throw;
            }

            m_file = pFileName;
            // allocate buffer according to fileinfo
            m_BufSize = (GenICam_streamsize)m_pAdapter->getBufSize(m_file.c_str(), mode);
            m_pBuffer = new char_type[(unsigned int)m_BufSize / sizeof(char_type)];

            // setg(buffer+pbSize, buffer+pbSize, buffer+pbSize);
            setg(m_pBuffer, m_pBuffer + m_BufSize,m_pBuffer + m_BufSize);

        #ifdef _MSC_VER
        // is this reasonable?
            std::basic_streambuf<CharType, Traits>::_Init();
        #endif

            return this;
        }



        bool
            is_open() const
        {
            return m_pAdapter != 0;
        }

        filebuf_type *close() {
            filebuf_type * ret = 0;
            if (this->is_open()) {
                // close file
                if(m_pAdapter->closeFile(m_file.c_str())){
                    // no error
                    ret = this;
                }
                delete m_pAdapter;
                m_pAdapter = 0;
                // buffer
                delete[] m_pBuffer;
                m_pBuffer = 0;
            }
            return ret;
        }


    protected:
        int_type underflow() {
            if (gptr() < egptr() )
                return traits_type::to_int_type(*gptr());

            if (buffer_in() < 0)
                return traits_type::eof();
            else
                return traits_type::to_int_type(*gptr());

        }

        int_type pbackfail(int_type c) {
            if (gptr() != eback() || eback()<gptr()) {
                gbump(-1);
                if (!traits_type::eq_int_type(c, traits_type::eof() ) )
                    *(gptr()) = static_cast<char_type>(traits_type::not_eof(c));
                return traits_type::not_eof(c);
            } else
                return traits_type::eof();
        }

    private:
        char_type * m_pBuffer;
        GenICam_streamsize m_BufSize;

        GENICAM_NAMESPACE::gcstring m_file;
        FileProtocolAdapter * m_pAdapter;
        int64_t m_fpos;



        int buffer_in() {

            GenICam_streamsize retval = m_pAdapter->read(m_pBuffer, m_fpos, m_BufSize, m_file.c_str());

            if (retval <= 0) {
                setg(0, 0, 0);
                return -1;
            } else {
                setg(m_pBuffer, m_pBuffer , m_pBuffer + retval);
                m_fpos += retval;
                return GENICAM_NAMESPACE::INTEGRAL_CAST2<int, GenICam_streamsize>(retval);
            }
        }


        // prohibit copying and assignment
        IDevFileStreamBuf(const IDevFileStreamBuf&);
        IDevFileStreamBuf& operator=(const IDevFileStreamBuf&);
    };


    template<typename CharType, typename Traits> class ODevFileStreamBuf
        : public std::basic_streambuf<CharType, Traits> {
            typedef Traits traits_type;

            typedef typename Traits::int_type int_type;
            typedef typename Traits::char_type char_type;
            typedef typename Traits::pos_type pos_type;
            typedef typename Traits::off_type off_type;

            typedef ODevFileStreamBuf<CharType, Traits> filebuf_type;


            // PUT begin
            using std::basic_streambuf<CharType, Traits>::pbase;
            // PUT next
            using std::basic_streambuf<CharType, Traits>::pptr;
            // PUT end
            using std::basic_streambuf<CharType, Traits>::epptr;
            // increment next pointer
            using std::basic_streambuf<CharType, Traits>::pbump;

    public:
        ODevFileStreamBuf()
            : m_pBuffer(0), m_file(0), m_pAdapter(0), m_fpos(0) {
        }

        ~ODevFileStreamBuf() {
            this->close();
        }

        filebuf_type *open(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName, std::ios_base::openmode mode) {

            // create Genicam Access
            m_pAdapter = new FileProtocolAdapter();

            // attach to nodemap
            if (!m_pAdapter || !m_pAdapter->attach(pInterface)){
                delete m_pAdapter;
                m_pAdapter = 0;
                return 0;
            }


            // open file via Adapter
            try
            {
                if (!(m_pAdapter->openFile(pFileName, mode))){
                    delete m_pAdapter;
                    m_pAdapter = 0;
                    return 0;
                }
            }
            catch (...)
            {
                delete m_pAdapter;
                m_pAdapter = 0;
                throw;
            }

            m_file = pFileName;
            // allocate buffer according to fileinfo
            const int64_t bufSize = m_pAdapter->getBufSize(m_file,mode);
            m_pBuffer = new char_type[GENICAM_NAMESPACE::INTEGRAL_CAST<size_t>(bufSize) / sizeof(char_type)];
            std::basic_streambuf<CharType, Traits>::setp(m_pBuffer, m_pBuffer + bufSize);

            return this;
        }

        bool
            is_open() const {
                return m_pAdapter != 0;
        }

        filebuf_type *close() {
            filebuf_type * ret = 0;
            bool syncFailed = false;
            if (this->is_open()) {
                if (sync()){
                    syncFailed = true;
                };
                // close file
                if(m_pAdapter->closeFile(m_file)){
                    // no error
                    if ( syncFailed ){
                        ret = 0;
                    } else {
                    ret = this;
                }
                }
                delete m_pAdapter;
                m_pAdapter = 0;
                // buffer
                delete[] m_pBuffer;
                m_pBuffer = 0;
            }
            return ret;
        }

    protected:
        GenICam_streamsize xsputn(const char_type * s, GenICam_streamsize n) {
            if (n < epptr() - pptr() ) {
                memcpy( pptr(), s, (size_t)(n * sizeof(char_type)));
                pbump( GENICAM_NAMESPACE::INTEGRAL_CAST2<int>(n) );
                return n;
            } else {
                for (GenICam_streamsize i = 0; i<n; ++i) {
                    if (traits_type::eq_int_type(std::basic_streambuf<CharType, Traits>::sputc(s[i]), traits_type::eof()))
                        return i;
                }
                return n;
            }

        }
        int_type overflow(int_type c = traits_type::eof()) {
            if (buffer_out() < 0) {
                return traits_type::eof();
            } else {
                if (!traits_type::eq_int_type (c, traits_type::eof() ) )
                    return std::basic_streambuf<CharType, Traits>::sputc(static_cast<char_type>(c));
                else
                    return traits_type::not_eof(c);
            }

        }
        int sync() {
            return GENICAM_NAMESPACE::INTEGRAL_CAST<int>(buffer_out());
        }

    private:
        char_type * m_pBuffer; // buffer[bufSize];
        const char * m_file;
        FileProtocolAdapter * m_pAdapter;
        int64_t m_fpos;

        int64_t buffer_out() {
            int64_t cnt = pptr() - pbase();

            int64_t retval;
            int64_t res = m_pAdapter->write(m_pBuffer, m_fpos, cnt, m_file);

            if (res != cnt) {
                retval = -1;
            } else {
                retval = 0;
            }
            m_fpos += res;

            pbump(- GENICAM_NAMESPACE::INTEGRAL_CAST<int>(cnt));
            return retval;
        }

        // prohibit copying assignment
        ODevFileStreamBuf(const ODevFileStreamBuf&);
        ODevFileStreamBuf & operator =(const ODevFileStreamBuf&);
    };

    template<typename CharType, typename Traits> class ODevFileStreamBase
        : public std::basic_ostream<CharType, Traits> {
    public:
        // Non-standard types:
        typedef ODevFileStreamBuf<CharType, Traits> filebuf_type;
        typedef std::basic_ios<CharType, Traits> ios_type;
        typedef std::basic_ostream<CharType, Traits> ostream_type;

    private:
        filebuf_type m_streambuf;
    public:

#if defined (_MSC_VER)
        ODevFileStreamBase()
            : ostream_type(std::_Noinit), m_streambuf() {
                this->init(&m_streambuf);
        }

        ODevFileStreamBase(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName, std::ios_base::openmode mode = std::ios_base::out|std::ios_base::trunc)
            : ostream_type(std::_Noinit), m_streambuf() {
                this->init(&m_streambuf);
                this->open(pInterface, pFileName, mode);
        }
        ;

#elif defined (__GNUC__)
        ODevFileStreamBase()
            : ostream_type(), m_streambuf() {
                this->init(&m_streambuf);
        }

        ODevFileStreamBase(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName, std::ios_base::openmode mode = std::ios_base::out|std::ios_base::trunc)
            : ostream_type(), m_streambuf() {
                this->init(&m_streambuf);
                this->open(pInterface, pFileName, mode);
        }
        ;


#else
#   error Unknown C++ library
#endif



        filebuf_type *rdbuf() const {
            return const_cast<filebuf_type*>(&m_streambuf);
        }

        /* bool is_open() {
            return m_streambuf.is_open();
        } */

        bool is_open() const {
            return m_streambuf.is_open();
        }

        /**
        *  @brief
        *   Open file on device in write mode
        *
        *  @param  pInterface  NodeMap of the device to which the FileProtocolAdapter is attached
        *  @param  pFileName  Name of the file to open
        *  @param  mode open mode
        *
        */
        void open(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName,
            std::ios_base::openmode mode = std::ios_base::out | std::ios_base::trunc) {
                if (!m_streambuf.open(pInterface,pFileName, mode)){
                    this->setstate(std::ios_base::failbit);
                }
                else{
                    this->clear();
                }
        }

        /**
        *  @brief  Close the file on device
        *
        */
        void close() {
            if (!m_streambuf.close())
                this->setstate(std::ios_base::failbit);
        }
    };

    template<typename CharType, typename Traits> class IDevFileStreamBase
        : public std::basic_istream<CharType, Traits> {
    public:

        // Non-standard types:
        typedef IDevFileStreamBuf<CharType, Traits> filebuf_type;
        typedef std::basic_ios<CharType, Traits> ios_type;
        typedef std::basic_istream<CharType, Traits> istream_type;

    private:
        filebuf_type m_streambuf;
    public:

#if defined (_MSC_VER)
        IDevFileStreamBase()
            : istream_type(std::_Noinit), m_streambuf() {
                this->init(&m_streambuf);
        }

        IDevFileStreamBase(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName,
            std::ios_base::openmode mode = std::ios_base::in)
            : istream_type(std::_Noinit), m_streambuf() {
                this->init(&m_streambuf);
                this->open(pInterface, pFileName, mode);
        }
        ;

#elif defined (__APPLE__)
        IDevFileStreamBase()
            : istream_type(0), m_streambuf() {
            this->init(&m_streambuf);
        }

        IDevFileStreamBase(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName,
            std::ios_base::openmode mode = std::ios_base::in)
            : istream_type(0), m_streambuf() {
            this->init(&m_streambuf);
            this->open(pInterface, pFileName, mode);
        }
        ;
        
#elif defined (__GNUC__)
        IDevFileStreamBase()
            : istream_type(), m_streambuf() {
                this->init(&m_streambuf);
        }

        IDevFileStreamBase(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName,
            std::ios_base::openmode mode = std::ios_base::in)
            : istream_type(), m_streambuf() {
                this->init(&m_streambuf);
                this->open(pInterface, pFileName, mode);
        }
        ;

#else
#   error Unknown C++ library
#endif


        filebuf_type *rdbuf() const {
            return const_cast<filebuf_type*>(&m_streambuf);
        }

        /* bool is_open() {
            return m_streambuf.is_open();
        } */

        bool is_open() const {
            return m_streambuf.is_open();
        }

        /* @brief
        *   Open file on device in write mode
        *
        *  @param  pInterface  NodeMap of the device to which the FileProtocolAdapter is attached
        *  @param  pFileName  Name of the file to open
        *  @param  mode open mode
        */
        void open(GENAPI_NAMESPACE::INodeMap * pInterface, const char * pFileName,
            std::ios_base::openmode mode = std::ios_base::in) {
                if (!m_streambuf.open(pInterface,pFileName, mode))
                    this->setstate(std::ios_base::failbit);
                else
                    this->clear();
        }

        /**
        *  @brief  Close the file on the device
        */
        void close() {
            if (!m_streambuf.close())
                this->setstate(std::ios_base::failbit);
        }
    };

    typedef ODevFileStreamBase<char, std::char_traits<char> > ODevFileStream;
    typedef IDevFileStreamBase<char, std::char_traits<char> > IDevFileStream;
}

#if defined (_MSC_VER)
#   pragma warning(pop)
#endif


#endif /*GENAPI_FILESTREAM_H_*/
